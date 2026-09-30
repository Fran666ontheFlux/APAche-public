"""Petit serveur local : sert l'interface et une API JSON.

Il n'écoute que sur 127.0.0.1. Une page web quelconque ouverte dans le même
navigateur peut toutefois envoyer des requêtes à 127.0.0.1 : on refuse donc
tout ce qui ne vient pas de notre propre page (en-têtes Host et Origin), et les
modifications exigent un corps JSON, ce qu'un simple formulaire ne peut pas envoyer.
"""

from __future__ import annotations

import json
import mimetypes
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import (apa, en_ligne, export, fichiers, import_bibliographie, import_dossiers, import_extraits, mise_en_forme,
               ocr, recherche, suggestions, vues)
from .application import Application
from .modele import DonneesInvalides, Extrait, Source
from .depot import ConfirmationRequise
from .stockage import ErreurStockage

DOSSIER_INTERFACE = Path(__file__).resolve().parent / "interface"
PORT_PAR_DEFAUT = 8765


class ErreurRequete(Exception):
    def __init__(self, statut: int, message: str):
        self.statut = statut
        super().__init__(message)


def _vue_projet(app: Application) -> dict:
    m = app.memoire
    comptes: dict[str, int] = {}
    for e in m.extraits.values():
        for id_ in e.mots_cles:
            comptes[id_] = comptes.get(id_, 0) + 1
    return {
        "projet": m.projet.vers_dict(),
        "mots_cles": [
            {**mot.vers_dict(), "nb_extraits": comptes.get(mot.id, 0)}
            for mot in sorted(m.mots_cles.values(), key=lambda x: x.libelle.casefold())
        ],
    }


def _chemin_fichier(corps: dict) -> Path:
    # Les guillemets viennent de « Copier en tant que chemin d'accès » de l'Explorateur.
    chemin = str(corps.get("chemin") or "").strip().strip('"')
    if not chemin:
        raise DonneesInvalides("Indique le chemin du fichier .docx à importer.")
    return Path(chemin)


def _onglets_choisis(corps: dict) -> list[str] | None:
    onglets = corps.get("onglets")
    if onglets is not None and not (isinstance(onglets, list) and all(isinstance(o, str) for o in onglets)):
        raise ErreurRequete(400, "Requête illisible.")
    return onglets


def _creer_source(app: Application, corps: dict) -> dict:
    donnees = vues.filtrer(corps, vues.CHAMPS_SOURCE_MODIFIABLES)
    source = app.memoire.ajouter_source(Source(**{"type": "article_revue", **donnees}))
    return {"cree": source.id, **vues.vue_source(app.memoire, source.id)}


def _creer_extrait(app: Application, source_id: str, corps: dict) -> dict:
    donnees = vues.filtrer(corps, vues.CHAMPS_EXTRAIT_MODIFIABLES)
    extrait = app.memoire.ajouter_extrait(Extrait(source_id=source_id, **donnees))
    return {"cree": extrait.id, **vues.vue_source(app.memoire, source_id)}


def _modifier_extrait(app: Application, id_: str, corps: dict) -> dict:
    extrait = app.memoire.modifier_extrait(id_, **vues.filtrer(corps, vues.CHAMPS_EXTRAIT_MODIFIABLES))
    return vues.vue_source(app.memoire, extrait.source_id)


def _supprimer_extrait(app: Application, id_: str) -> dict:
    source_id = app.memoire._extrait(id_).source_id
    app.memoire.supprimer_extrait(id_)
    return vues.vue_source(app.memoire, source_id)


def _appliquer_biblio(app: Application, corps: dict) -> dict:
    empreinte, action = corps.get("empreinte"), corps.get("action")
    if not isinstance(empreinte, str) or not isinstance(action, str):
        raise ErreurRequete(400, "Requête illisible.")
    chemin = _chemin_fichier(corps)
    fait = import_bibliographie.appliquer(app.memoire, chemin, empreinte, action, corps.get("source_id"))
    return {**fait, **import_bibliographie.apercu(app.memoire, chemin)}


def _texte_source(app: Application, id_: str) -> dict:
    m = app.memoire
    source = m._source(id_)
    chemin = m.chemin_fichier(source)
    if not chemin or not chemin.exists():
        raise DonneesInvalides("Le fichier joint est introuvable dans le dossier de données. Si tu viens de "
                               "l'ajouter sur un autre PC, attends la fin de la synchronisation.")
    return fichiers.texte_du_fichier(chemin, source.premiere_page, m.dossier / recherche.DOSSIER_INDEX)


def _dossier(corps: dict) -> Path:
    chemin = str(corps.get("chemin") or "").strip().strip('"')
    if not chemin:
        raise DonneesInvalides("Indique le chemin du dossier qui contient tes PDF.")
    return Path(chemin)


def _appliquer_dossier(app: Application, corps: dict) -> dict:
    empreinte, action = corps.get("empreinte"), corps.get("action")
    if not isinstance(empreinte, str) or not isinstance(action, str):
        raise ErreurRequete(400, "Requête illisible.")
    return import_dossiers.appliquer(app.memoire, _dossier(corps), empreinte, action, corps.get("source_id"))


def _ocr_source(app: Application, id_: str) -> dict:
    m = app.memoire
    chemin = m.chemin_fichier(m._source(id_))
    if not chemin or not chemin.exists():
        raise DonneesInvalides("Aucun fichier joint à lire.")
    return ocr.avancer(chemin, m.dossier / recherche.DOSSIER_INDEX)


def _chercher_en_ligne(app: Application, corps: dict) -> dict:
    """DOI ou ISBN → proposition de référence. Refusé tant que l'utilisateur ne l'a pas
    autorisé dans le projet : même un appel venu d'une erreur de l'interface ne sort pas."""
    if not app.memoire.projet.recherche_en_ligne:
        raise ErreurRequete(403, "La recherche en ligne est désactivée. Active-la dans l'écran Projet, "
                                 "ou remplis la référence à la main.")
    identifiant = corps.get("identifiant")
    if not isinstance(identifiant, str) or not identifiant.strip():
        raise DonneesInvalides("Indique un DOI ou un ISBN.")
    proposition = en_ligne.chercher(identifiant)
    source = Source(type=proposition["type"], auteurs=proposition["auteurs"], annee=proposition["annee"],
                    titre=proposition["titre"], champs=proposition["champs"])
    source.valider()
    mise = apa.reference(source, app.memoire.projet.reglages_apa)
    return {"proposition": proposition, "reference": {"html": mise.html, "texte": mise.texte} if mise else None}



# Chaque route : (méthode, motif d'URL, fonction(app, corps, params, *groupes)).
# Les modifications renvoient la vue complète du projet : l'interface n'a
# qu'à se redessiner, sans tenir de copie des données qui pourrait diverger.
ROUTES = [
    ("GET", r"/api/etat", lambda app, c, q: app.etat()),
    ("POST", r"/api/ouvrir", lambda app, c, q: app.ouvrir(c.get("dossier"), bool(c.get("forcer")), bool(c.get("creer")))),
    ("GET", r"/api/projet", lambda app, c, q: _vue_projet(app)),
    ("PATCH", r"/api/projet",
     lambda app, c, q: (app.memoire.modifier_projet(**c), _vue_projet(app))[1]),
    ("POST", r"/api/mots-cles",
     lambda app, c, q: {"cree": app.memoire.ajouter_mot_cle(**vues.filtrer(c, {"libelle", "parent_id", "synonymes", "couleur"})).id,
                        **_vue_projet(app)}),
    ("PATCH", r"/api/mots-cles/(\w+)",
     lambda app, c, q, id_: (app.memoire.modifier_mot_cle(id_, **c), _vue_projet(app))[1]),
    ("DELETE", r"/api/mots-cles/(\w+)",
     lambda app, c, q, id_: (app.memoire.supprimer_mot_cle(id_, confirme=q.get("confirme") == "1"),
                             _vue_projet(app))[1]),
    ("POST", r"/api/mots-cles/(\w+)/fusionner",
     lambda app, c, q, id_: (app.memoire.fusionner_mots_cles(id_, c.get("absorber", "")),
                             _vue_projet(app))[1]),
    ("GET", r"/api/schema", lambda app, c, q: vues.schema()),
    ("GET", r"/api/extraits", lambda app, c, q: vues.vue_extraits(app.memoire)),
    ("POST", r"/api/suggestions",
     lambda app, c, q: {"suggestions": suggestions.suggerer(app.memoire, mise_en_forme.brut(str(c.get("texte") or "")))}),
    ("GET", r"/api/mots-cles/mesure", lambda app, c, q: suggestions.mesurer(app.memoire)),
    ("GET", r"/api/bibliographie", lambda app, c, q: vues.vue_bibliographie(app.memoire)),
    ("POST", r"/api/en-ligne", lambda app, c, q: _chercher_en_ligne(app, c)),
    ("POST", r"/api/recherche/indexer", lambda app, c, q: recherche.indexer(app.memoire)),
    ("GET", r"/api/ocr", lambda app, c, q: {k: v for k, v in ocr.outil().items() if k in ("disponible", "message")}),
    ("POST", r"/api/sources/(\w+)/ocr", lambda app, c, q, id_: _ocr_source(app, id_)),
    ("GET", r"/api/recherche", lambda app, c, q: recherche.rechercher(app.memoire, q.get("q", ""))),
    ("GET", r"/api/plan", lambda app, c, q: vues.vue_plan(app.memoire)),
    ("POST", r"/api/plan",
     lambda app, c, q: {"cree": app.memoire.ajouter_section(**vues.filtrer(c, {"titre", "niveau", "mots_cles", "apres"})).id,
                        **vues.vue_plan(app.memoire)}),
    ("GET", r"/api/plan/(\w+)", lambda app, c, q, id_: vues.vue_section(app.memoire, id_)),
    ("PATCH", r"/api/plan/(\w+)",
     lambda app, c, q, id_: (app.memoire.modifier_section(id_, **c), vues.vue_plan(app.memoire))[1]),
    ("POST", r"/api/plan/(\w+)/deplacer",
     lambda app, c, q, id_: (app.memoire.deplacer_section(id_, str(c.get("sens"))), vues.vue_plan(app.memoire))[1]),
    ("DELETE", r"/api/plan/(\w+)",
     lambda app, c, q, id_: (app.memoire.supprimer_section(id_, confirme=q.get("confirme") == "1"),
                             vues.vue_plan(app.memoire))[1]),
    ("GET", r"/api/sources", lambda app, c, q: vues.vue_sources(app.memoire)),
    ("POST", r"/api/sources", lambda app, c, q: _creer_source(app, c)),
    ("POST", r"/api/sources/apercu", lambda app, c, q: vues.apercu_reference(app.memoire, c)),
    ("GET", r"/api/sources/(\w+)", lambda app, c, q, id_: vues.vue_source(app.memoire, id_)),
    ("GET", r"/api/sources/(\w+)/texte", lambda app, c, q, id_: _texte_source(app, id_)),
    ("PATCH", r"/api/sources/(\w+)",
     lambda app, c, q, id_: (app.memoire.modifier_source(id_, **vues.filtrer(c, vues.CHAMPS_SOURCE_MODIFIABLES)),
                             vues.vue_source(app.memoire, id_))[1]),
    ("DELETE", r"/api/sources/(\w+)",
     lambda app, c, q, id_: (app.memoire.supprimer_source(id_, confirme=q.get("confirme") == "1"),
                             vues.vue_sources(app.memoire))[1]),
    ("POST", r"/api/sources/(\w+)/extraits", lambda app, c, q, id_: _creer_extrait(app, id_, c)),
    ("PATCH", r"/api/extraits/(\w+)", lambda app, c, q, id_: _modifier_extrait(app, id_, c)),
    ("DELETE", r"/api/extraits/(\w+)", lambda app, c, q, id_: _supprimer_extrait(app, id_)),
    ("POST", r"/api/import/bibliographie/apercu",
     lambda app, c, q: import_bibliographie.apercu(app.memoire, _chemin_fichier(c))),
    ("POST", r"/api/import/bibliographie/appliquer", lambda app, c, q: _appliquer_biblio(app, c)),
    ("POST", r"/api/import/dossiers/apercu", lambda app, c, q: import_dossiers.apercu(app.memoire, _dossier(c))),
    ("POST", r"/api/import/dossiers/appliquer", lambda app, c, q: _appliquer_dossier(app, c)),
    ("POST", r"/api/import/apercu",
     lambda app, c, q: import_extraits.apercu(app.memoire, _chemin_fichier(c))),
    ("POST", r"/api/import/extraits",
     lambda app, c, q: {"rapport": import_extraits.importer(app.memoire, _chemin_fichier(c), _onglets_choisis(c)),
                        **_vue_projet(app)}),
]
ROUTES_SANS_MEMOIRE = {"/api/etat", "/api/ouvrir", "/api/fermer", "/api/schema"}


class Gestionnaire(BaseHTTPRequestHandler):
    app: Application  # fixé par creer_serveur
    serveur_a_arreter: callable

    def log_message(self, format, *args):
        # Le journal par défaut noierait la fenêtre de lancement sous les requêtes.
        pass

    def end_headers(self):
        # Aucun site ne peut afficher l'outil dans un cadre invisible pour faire cliquer
        # « Supprimer » à l'insu de l'utilisateur (clickjacking) ; pas de type deviné.
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _hote_autorise(self) -> bool:
        port = self.server.server_address[1]
        autorises = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in autorises:
            return False
        origine = self.headers.get("Origin")
        return origine is None or origine in {f"http://{h}" for h in autorises}

    def _vider_corps(self) -> None:
        """Lire ce que la requête envoie encore avant de répondre. Une requête refusée
        d'emblée (autre site, mauvais type) laisse sinon des octets non lus, et Windows
        coupe alors la connexion avant que la réponse n'arrive."""
        reste = int(self.headers.get("Content-Length") or 0) - getattr(self, "_octets_lus", 0)
        if 0 < reste <= 1 << 20:
            self.rfile.read(reste)
            self._octets_lus = getattr(self, "_octets_lus", 0) + reste
        elif reste > 0:
            self.close_connection = True  # trop gros pour être lu pour rien : on ferme franchement

    def _repondre(self, statut: int, corps: bytes, type_: str) -> None:
        self._vider_corps()
        self.send_response(statut)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def _repondre_json(self, statut: int, donnees) -> None:
        self._repondre(statut, json.dumps(donnees, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

    def _servir_fichier(self, chemin: str) -> None:
        relatif = "index.html" if chemin in ("", "/") else chemin.lstrip("/")
        fichier = (DOSSIER_INTERFACE / relatif).resolve()
        if DOSSIER_INTERFACE not in fichier.parents or not fichier.is_file():
            self._repondre_json(404, {"erreur": "Page introuvable."})
            return
        type_ = mimetypes.guess_type(fichier.name)[0] or "application/octet-stream"
        if type_.startswith("text/") or type_ == "application/javascript":
            type_ += "; charset=utf-8"
        self._repondre(200, fichier.read_bytes(), type_)

    def _lire_corps(self) -> dict:
        longueur = int(self.headers.get("Content-Length") or 0)
        if not longueur:
            return {}
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise ErreurRequete(415, "Requête refusée.")
        try:
            brut = self.rfile.read(longueur)
            self._octets_lus = longueur
            corps = json.loads(brut.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ErreurRequete(400, "Requête illisible.") from None
        if not isinstance(corps, dict):
            raise ErreurRequete(400, "Requête illisible.")
        return corps

    def _traiter(self, methode: str) -> None:
        self._octets_lus = 0  # une connexion peut porter plusieurs requêtes : on repart de zéro
        if not self._hote_autorise():
            self._repondre_json(403, {"erreur": "Accès refusé."})
            return
        url = urlparse(self.path)
        if methode == "GET" and not url.path.startswith("/api/"):
            self._servir_fichier(url.path)
            return
        try:
            fichier = re.fullmatch(r"/api/sources/(\w+)/fichier", url.path)
            if fichier:
                self._route_fichier(methode, fichier.group(1))
                return
            if methode != "GET" and self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ErreurRequete(415, "Requête refusée.")
            corps = self._lire_corps()
            params = {k: v[-1] for k, v in parse_qs(url.query).items()}
            if methode == "GET" and url.path == "/api/export":
                self._exporter(params)
                return
            if methode == "POST" and url.path == "/api/fermer":
                self.app.fermer()
                self._repondre_json(200, {"ferme": True})
                self.serveur_a_arreter()
                return
            for m, motif, action in ROUTES:
                trouve = re.fullmatch(motif, url.path)
                if m == methode and trouve:
                    with self.app.acces:
                        if self.app.memoire is None and url.path not in ROUTES_SANS_MEMOIRE:
                            raise ErreurRequete(409, "Aucun mémoire n'est ouvert.")
                        resultat = action(self.app, corps, params, *trouve.groups())
                    self._repondre_json(200, resultat)
                    return
            raise ErreurRequete(404, "Action inconnue.")
        except ErreurRequete as e:
            self._repondre_json(e.statut, {"erreur": str(e)})
        except ConfirmationRequise as e:
            self._repondre_json(409, {"confirmation": str(e), "nombre": e.nombre})
        except DonneesInvalides as e:
            self._repondre_json(400, {"erreur": str(e)})
        except ErreurStockage as e:
            self._repondre_json(500, {"erreur": str(e)})
        except Exception:
            traceback.print_exc()
            self._repondre_json(500, {"erreur": (
                "Erreur inattendue. Tes données déjà enregistrées ne sont pas touchées. "
                "Le détail technique est affiché dans la fenêtre noire de lancement : "
                "copie-le si tu veux le signaler.")})

    def _exporter(self, params: dict) -> None:
        """Le fichier RIS ou BibTeX, à enregistrer par le navigateur (et non une page à afficher)."""
        format_ = params.get("format", "ris")
        if format_ not in ("ris", "bibtex") or params.get("sources", "citees") not in ("citees", "toutes"):
            raise ErreurRequete(400, "Format d'export inconnu.")
        with self.app.acces:
            if self.app.memoire is None:
                raise ErreurRequete(409, "Aucun mémoire n'est ouvert.")
            sources = export.sources_a_exporter(self.app.memoire, params.get("sources", "citees"))
            texte = export.ris(sources) if format_ == "ris" else export.bibtex(sources)
        nom = f"memoire-{params.get('sources', 'citees')}.{'ris' if format_ == 'ris' else 'bib'}"
        corps = texte.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-research-info-systems; charset=utf-8" if format_ == "ris"
                         else "application/x-bibtex; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Content-Disposition", f'attachment; filename="{nom}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def _route_fichier(self, methode: str, id_: str) -> None:
        """Le fichier joint : l'envoyer (ouvrir le PDF), ou le recevoir (glisser-déposer).

        Le fichier arrive brut, en application/octet-stream : un formulaire d'un
        autre site ne peut pas envoyer ce type sans l'accord du serveur, qui ne le
        donne jamais. Le nom voyage dans un en-tête, encodé.
        """
        with self.app.acces:
            m = self.app.memoire
            if m is None:
                raise ErreurRequete(409, "Aucun mémoire n'est ouvert.")
            if methode == "GET":
                source = m._source(id_)
                chemin = m.chemin_fichier(source)
                if not chemin or not chemin.exists():
                    raise ErreurRequete(404, "Aucun fichier joint à cette source.")
                contenu = chemin.read_bytes()
                type_ = fichiers.EXTENSIONS.get(chemin.suffix.lower(), "application/octet-stream")
            elif methode == "POST":
                if self.headers.get("Content-Type", "").split(";")[0] != "application/octet-stream":
                    raise ErreurRequete(415, "Requête refusée.")
                longueur = int(self.headers.get("Content-Length") or 0)
                if longueur > fichiers.TAILLE_MAX:
                    raise ErreurRequete(413, f"Fichier trop lourd (plus de {fichiers.TAILLE_MAX // (1024 * 1024)} Mo).")
                nom = unquote(self.headers.get("X-Nom-Fichier", ""))
                contenu = self.rfile.read(longueur)
                self._octets_lus = longueur
                m.joindre_fichier(id_, nom, contenu)
                vue = vues.vue_source(m, id_)
            else:
                raise ErreurRequete(404, "Action inconnue.")
        if methode == "GET":
            self.send_response(200)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(contenu)))
            self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(chemin.name)}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(contenu)
        else:
            self._repondre_json(200, vue)

    def do_GET(self):
        self._traiter("GET")

    def do_POST(self):
        self._traiter("POST")

    def do_PATCH(self):
        self._traiter("PATCH")

    def do_DELETE(self):
        self._traiter("DELETE")


def creer_serveur(app: Application, port: int = PORT_PAR_DEFAUT) -> ThreadingHTTPServer:
    serveur = ThreadingHTTPServer(("127.0.0.1", port), Gestionnaire)
    serveur.daemon_threads = True

    class GestionnaireLie(Gestionnaire):
        pass

    GestionnaireLie.app = app
    # shutdown() attend la fin de serve_forever : l'appeler depuis le fil qui
    # traite la requête bloquerait. On le lance donc à côté.
    GestionnaireLie.serveur_a_arreter = staticmethod(
        lambda: threading.Thread(target=serveur.shutdown, daemon=True).start())
    serveur.RequestHandlerClass = GestionnaireLie
    return serveur


mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
