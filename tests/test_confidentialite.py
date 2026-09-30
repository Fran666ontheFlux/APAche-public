"""Confidentialité : le mémoire reste sur le PC de l'utilisateur.

- le serveur n'écoute que sur la machine elle-même (127.0.0.1), jamais sur le réseau ;
- aucune page d'un autre site, ouverte dans le même navigateur, ne peut lire ni modifier les données ;
- l'outil n'appelle jamais internet : ni dans son code, ni pendant une séance de travail.
  Seule exception, désactivée par défaut : chercher un DOI ou un ISBN, sur clic, si
  l'utilisateur l'a autorisé — vers CrossRef et Open Library seulement ;
- aucune donnée personnelle ne peut entrer dans le dépôt git (qui part sur GitHub).

Ces tests gardent ces promesses vraies pour les versions suivantes (V2 : DOI, ISBN…) :
un appel réseau ajouté plus tard devra être voulu, et inscrit ici.
"""

import ast
import http.client
import json
import re
import socket
import subprocess
from pathlib import Path

from outils import RACINE, dossier_temporaire, lancer

from test_sources_serveur import avec_client

CODE = RACINE / "memoire"
INTERFACE = CODE / "interface"

# Modules capables de parler au réseau. Chacun n'est permis que là où il est inscrit ici, avec sa raison.
MODULES_RESEAU = {"urllib.request", "http.client", "requests", "httpx", "aiohttp", "smtplib", "ftplib",
                  "telnetlib", "imaplib", "poplib", "socketserver", "xmlrpc.client", "webbrowser", "socket"}
PERMIS = {
    ("__main__.py", "urllib.request"): "savoir si l'outil tourne déjà : appel à 127.0.0.1 seulement",
    ("__main__.py", "webbrowser"): "ouvrir la page de l'outil, sur 127.0.0.1",
    ("verrou.py", "socket"): "le nom du PC, pour le verrou (gethostname, aucune connexion)",
    ("en_ligne.py", "urllib.request"): "DOI → CrossRef, ISBN → Open Library : sur demande, si l'utilisateur l'a autorisé",
}


def requete_brute(client, methode, chemin, entetes, corps=None):
    connexion = http.client.HTTPConnection("127.0.0.1", client.port, timeout=5)
    connexion.putrequest(methode, chemin, skip_host=True, skip_accept_encoding=True)
    for cle, valeur in entetes.items():
        connexion.putheader(cle, valeur)
    donnees = json.dumps(corps).encode() if corps is not None else b""
    if donnees:
        connexion.putheader("Content-Length", str(len(donnees)))
    connexion.endheaders(donnees or None)
    reponse = connexion.getresponse()
    corps_reponse = reponse.read()
    connexion.close()
    return reponse.status, dict(reponse.getheaders()), corps_reponse


# --- 1. Le serveur n'écoute que sur la machine -----------------------------------------

@avec_client
def test_serveur_injoignable_depuis_le_reseau(client):
    assert client.serveur.server_address[0] == "127.0.0.1"
    adresses = set()
    try:
        adresses = {a for a in socket.gethostbyname_ex(socket.gethostname())[2] if not a.startswith("127.")}
    except OSError:
        pass
    for adresse in adresses:  # l'adresse du PC sur le réseau local (Wi-Fi, câble)
        try:
            socket.create_connection((adresse, client.port), timeout=2).close()
            raise AssertionError(f"le serveur répond sur {adresse} : il est visible depuis le réseau")
        except OSError:
            pass  # refusé : c'est ce qu'on veut


# --- 2. Aucune page d'un autre site ne peut lire ni modifier -------------------------------

@avec_client
def test_autres_sites_refuses(client):
    local = f"127.0.0.1:{client.port}"
    cas = [
        # Rattachement DNS : un site pirate fait pointer son nom vers 127.0.0.1.
        ("GET", "/api/extraits", {"Host": f"pirate.example:{client.port}"}, None, 403),
        # Page d'un autre site qui appelle l'outil depuis le même navigateur.
        ("GET", "/api/extraits", {"Host": local, "Origin": "https://pirate.example"}, None, 403),
        ("POST", "/api/sources", {"Host": local, "Origin": "https://pirate.example",
                                  "Content-Type": "application/json"}, {"type": "livre"}, 403),
        # Formulaire d'un autre site (sans Origin, comme certains navigateurs) : type refusé.
        ("POST", "/api/sources", {"Host": local, "Content-Type": "text/plain"}, {"type": "livre"}, 415),
        ("POST", "/api/sources", {"Host": local, "Content-Type": "application/x-www-form-urlencoded"}, {"type": "livre"}, 415),
        ("POST", "/api/sources/x/fichier", {"Host": local, "Content-Type": "multipart/form-data"}, None, 415),
    ]
    for methode, chemin, entetes, corps, attendu in cas:
        statut, reponse, _ = requete_brute(client, methode, chemin, entetes, corps)
        assert statut == attendu, (methode, chemin, entetes, statut)
        assert "Access-Control-Allow-Origin" not in reponse  # aucun site n'est autorisé à lire les réponses
    _, liste = client("GET", "/api/sources")
    assert liste["sources"] == []  # aucune des tentatives n'a rien créé


@avec_client
def test_rien_hors_de_l_interface(client):
    local = {"Host": f"127.0.0.1:{client.port}"}
    for chemin in ("/../memoire.json", "/%2e%2e/%2e%2e/reglages.json", "/..%2f..%2fmemoire%2fdepot.py",
                   "/..\\..\\memoire\\depot.py", "/interface/../../memoire/depot.py", "//etc/passwd",
                   "/C:/Windows/win.ini"):
        statut, _, corps = requete_brute(client, "GET", chemin, local)
        assert statut == 404 and b"def " not in corps, (chemin, statut)


@avec_client
def test_aucun_site_ne_peut_afficher_l_outil_dans_un_cadre(client):
    """Contre le clickjacking : une page piégée ne peut pas charger l'outil dans un cadre invisible."""
    local = {"Host": f"127.0.0.1:{client.port}"}
    for chemin in ("/", "/api/etat", "/api/sources/inconnu"):
        _, entetes, _ = requete_brute(client, "GET", chemin, local)
        assert entetes.get("X-Frame-Options") == "DENY", chemin
        assert "frame-ancestors 'none'" in entetes.get("Content-Security-Policy", ""), chemin


# --- 3. L'outil n'appelle jamais internet --------------------------------------------------

def test_aucun_module_reseau_hors_de_ceux_permis():
    trouves = set()
    for fichier in CODE.rglob("*.py"):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            noms = []
            if isinstance(noeud, ast.Import):
                noms = [a.name for a in noeud.names]
            elif isinstance(noeud, ast.ImportFrom) and noeud.module:
                noms = [noeud.module] + [f"{noeud.module}.{a.name}" for a in noeud.names]
            for nom in noms:
                if nom in MODULES_RESEAU:
                    trouves.add((fichier.name, nom))
    assert trouves <= set(PERMIS), f"accès réseau non prévu : {sorted(trouves - set(PERMIS))}"


def test_les_seules_adresses_appelees_sont_locales():
    for fichier in CODE.rglob("*.py"):
        texte = fichier.read_text(encoding="utf-8")
        for m in re.finditer(r"urlopen\(\s*f?[\"']([^\"']+)", texte):
            assert m.group(1).startswith("http://127.0.0.1"), (fichier.name, m.group(1))
    assert "connect(" not in (CODE / "verrou.py").read_text(encoding="utf-8")


def test_l_interface_ne_charge_rien_d_internet():
    # Ni police Google, ni CDN, ni image distante, ni appel à un autre site : tout est dans le projet.
    motif = re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//|@import\s+url\(\s*["']?(?:https?:)?//|"""
                       r"""url\(\s*["']?(?:https?:)?//|fetch\(\s*[`"']\s*(?:https?:)?//|new\s+WebSocket|EventSource\(|sendBeacon""",
                       re.IGNORECASE)
    for fichier in INTERFACE.iterdir():
        if fichier.suffix in (".html", ".js", ".css"):
            trouve = motif.search(fichier.read_text(encoding="utf-8"))
            assert not trouve, f"{fichier.name} charge quelque chose d'internet : {trouve.group()}"


@avec_client
def test_une_seance_de_travail_n_ouvre_aucune_connexion_vers_l_exterieur(client):
    # On note toute connexion que le code du serveur ouvre pendant une séance complète.
    ouvertes = []
    origine = socket.socket.connect

    def espion(self, adresse):
        ouvertes.append(adresse)
        return origine(self, adresse)

    socket.socket.connect = espion
    try:
        _, vue = client("POST", "/api/sources", {"type": "article_revue", "titre": "T", "annee": "2020",
                                                 "auteurs": [{"nom": "Martin", "prenom": "A."}],
                                                 "champs": {"revue": "R", "doi": "10.9999/0042098016630507"}})
        client("POST", f"/api/sources/{vue['cree']}/extraits", {"texte": "x", "page_debut": "1", "nature": "citation",
                                                                 "integre": True})
        for chemin in ("/api/sources", f"/api/sources/{vue['cree']}", "/api/extraits", "/api/bibliographie",
                       "/api/projet", "/api/schema"):
            client("GET", chemin)
    finally:
        socket.socket.connect = origine
    # Les seules connexions sont celles du test vers le serveur local, jamais du serveur vers ailleurs.
    exterieures = [a for a in ouvertes if isinstance(a, tuple) and a[0] not in ("127.0.0.1", "localhost", "::1")]
    assert not exterieures, f"connexions vers l'extérieur : {exterieures}"


def test_recherche_en_ligne_limitee_aux_catalogues():
    texte = (CODE / "en_ligne.py").read_text(encoding="utf-8")
    adresses = set(re.findall(r"https?://[^\"'\s/]+", texte))
    # purl.org : le nom de l'espace XML Dublin Core, jamais appelé.
    assert adresses == {"https://api.crossref.org", "https://openlibrary.org", "https://catalogue.bnf.fr",
                        "https://doi.org", "http://purl.org"}, adresses
    assert "mailto" not in texte.casefold() and "@" not in re.sub(r"#.*", "", texte)  # jamais d'adresse e-mail envoyée
    importeurs = {f.name for f in CODE.rglob("*.py") if re.search(r"\ben_ligne\b", f.read_text(encoding="utf-8"))
                  and f.name != "en_ligne.py"}
    assert importeurs == {"serveur.py"}, importeurs  # une seule porte : la route appelée sur clic


@avec_client
def test_recherche_en_ligne_desactivee_par_defaut(client):
    ouvertes = []
    origine = socket.socket.connect
    socket.socket.connect = lambda self, adresse: (ouvertes.append(adresse), origine(self, adresse))[1]
    try:
        _, projet = client("GET", "/api/projet")
        statut, reponse = client("POST", "/api/en-ligne", {"identifiant": "10.9999/0042098016630507"})
    finally:
        socket.socket.connect = origine
    assert projet["projet"]["recherche_en_ligne"] is False
    assert statut == 403 and "désactivée" in reponse["erreur"]
    assert not [a for a in ouvertes if isinstance(a, tuple) and a[0] not in ("127.0.0.1", "localhost", "::1")]


# --- 4. Aucune donnée dans le dépôt git -----------------------------------------------------

def test_gitignore_protege_les_donnees():
    regles = {l.strip() for l in (RACINE / ".gitignore").read_text(encoding="utf-8").splitlines()}
    for indispensable in ("memoire.json", "verrou.json", "sauvegardes/", "fichiers/", "index/", "reglages_locaux.json",
                          "*.docx", "*.pdf"):
        assert indispensable in regles, f".gitignore doit exclure {indispensable}"


def test_aucun_fichier_de_donnees_suivi_par_git():
    try:
        suivis = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return  # git absent (copie du dossier sans dépôt) : rien à vérifier
    donnees = [f for f in suivis if re.search(r"\.(docx?|pdf|xlsx?|csv)$|(^|/)(memoire|verrou|reglages_locaux)\.json$"
                                              r"|(^|/)(sauvegardes|fichiers|index)/", f, re.IGNORECASE)]
    assert not donnees, f"données personnelles suivies par git : {donnees}"


if __name__ == "__main__":
    lancer(globals())
