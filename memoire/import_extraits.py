"""Import du Google Doc d'extraits de lecture, exporté en .docx.

Règles validées avec l'utilisateur après examen du vrai document :
- à l'export Word, chaque onglet devient un titre de style « Title » et la
  hiérarchie des onglets est perdue. Un onglet vide suivi d'un onglet rempli
  est un thème (→ mot-clé) ; les onglets remplis qui le suivent sont ses sources ;
- un extrait = un bloc de lignes entre deux lignes vides. Le texte copié d'un
  PDF arrive avec un paragraphe Word par ligne : un paragraphe n'est pas un extrait ;
- page notée à la fin ou au début du bloc (p12, (p. 12), pp12-14…), sinon vide.
  Une page en fin de ligne au milieu d'un bloc ferme elle aussi un passage :
  le bloc est coupé là (ligne vide oubliée après le numéro de page) ;
- bloc barré au moins à moitié → intégré ; barré en partie → note à vérifier ;
- page trouvée → citation, sinon paraphrase (une citation sans page est refusée) ;
- commentaires de marge → note de l'extrait ; notes de bas de page ignorées
  (ce sont celles des PDF d'origine, recopiées).

Le fichier d'origine n'est jamais modifié. L'import est rejouable sans doublon :
chaque objet créé retient d'où il vient dans `origine_import`.

Lecture par la bibliothèque standard plutôt que python-docx : celle-ci n'expose
pas les commentaires de marge ni leurs plages, qui peuvent couvrir plusieurs
paragraphes.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .depot import Memoire
from .modele import DonneesInvalides, Extrait, MotCle, Source

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
STYLES_ONGLET = {"Title", "Titre"}

# Onglets remplis qui ne sont pas des notes de lecture : décochés par défaut
# dans l'aperçu, l'utilisateur peut toujours les recocher.
ONGLETS_HORS_LECTURE = re.compile(
    r"^(liens?|r[ée]u(nion)?s?|meetings?|mails?|planning|brouillons?|final|copie de|onglet sans titre)\b",
    re.IGNORECASE)

# Mêmes teintes que l'interface (app.js), pour les thèmes créés par l'import.
PALETTE = ("#4f7cac", "#3f9d8f", "#6a9f4b", "#c29a2e", "#d0773c",
           "#c4545a", "#b0588f", "#7d62b5", "#5a6f8f", "#8c7a5b")

# Pages : p12, p. 12, pp12-14, (p14), p.18), p 2-3…
_NUMEROS = r"(?P<debut>\d+)(?:\s?[-–]\s?(?P<fin>\d+))?"
_MARQUE = rf"\(?\s?pp?\s?\.?\s?{_NUMEROS}\s?\)?"
# Le point final après la page compte encore comme fin : « … (p. 12). », « … p. 12. »
MARQUE_FIN = re.compile(rf"(?:^|(?<=[\s.,;:!?»”\"'’]))(?P<m>{_MARQUE})[.,;]?\s*$", re.IGNORECASE)
MARQUE_DEBUT = re.compile(rf"^\s*(?P<m>{_MARQUE})(?=\s|$)", re.IGNORECASE)
ANNEE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")

SEUIL_INTEGRE = 0.5


@dataclass
class Paragraphe:
    lignes: list[str]
    barres: int  # caractères barrés (espaces exclus)
    total: int
    commentaires: list[str]


@dataclass
class Bloc:
    paragraphes: list[Paragraphe] = field(default_factory=list)

    @property
    def lignes(self) -> list[str]:
        return [ligne for p in self.paragraphes for ligne in p.lignes]


@dataclass
class Onglet:
    titre: str
    blocs: list[Bloc] = field(default_factory=list)


@dataclass
class ExtraitLu:
    texte: str
    page_debut: str = ""
    page_fin: str = ""
    part_barree: float = 0.0
    commentaires: list[str] = field(default_factory=list)

    @property
    def integre(self) -> bool:
        return self.part_barree >= SEUIL_INTEGRE

    @property
    def barre_en_partie(self) -> bool:
        return 0 < self.part_barree < 1

    @property
    def empreinte(self) -> str:
        return hashlib.sha1(" ".join(self.texte.split()).casefold().encode("utf-8")).hexdigest()[:16]


@dataclass
class OngletLu:
    titre: str
    theme: str | None
    propose: bool
    extraits: list[ExtraitLu]


# --- Lecture du .docx ---------------------------------------------------------

def _actif(rpr, balise: str) -> bool:
    el = rpr.find(W + balise) if rpr is not None else None
    return el is not None and el.get(W + "val", "true").lower() not in ("0", "false", "none")


def _lire_commentaires(archive: zipfile.ZipFile) -> dict[str, str]:
    if "word/comments.xml" not in archive.namelist():
        return {}
    racine = ET.fromstring(archive.read("word/comments.xml"))
    commentaires = {}
    for c in racine.iter(W + "comment"):
        paragraphes = ["".join(t.text or "" for t in p.iter(W + "t")) for p in c.iter(W + "p")]
        texte = " ".join(p.strip() for p in paragraphes if p.strip())
        if texte:
            commentaires[c.get(W + "id")] = texte
    return commentaires


def ouvrir_docx(chemin: Path) -> tuple[ET.Element, dict[str, str]]:
    """Le corps du document et les commentaires de marge, avec des erreurs lisibles."""
    chemin = Path(chemin)
    if not chemin.is_file():
        raise DonneesInvalides(f"Le fichier « {chemin} » est introuvable. Vérifie le chemin "
                               f"(clic droit sur le fichier → « Copier en tant que chemin d'accès »).")
    try:
        with zipfile.ZipFile(chemin) as archive:
            return ET.fromstring(archive.read("word/document.xml")), _lire_commentaires(archive)
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise DonneesInvalides(
            f"« {chemin.name} » n'est pas un document Word lisible. Dans Google Docs : "
            f"Fichier → Télécharger → Microsoft Word (.docx), puis indique ce fichier-là.") from None
    except PermissionError:
        raise DonneesInvalides(f"Impossible de lire « {chemin.name} » : est-il ouvert dans Word ? "
                               f"Ferme-le et réessaie.") from None


def lire_onglets(chemin: Path) -> list[Onglet]:
    document, textes_commentaires = ouvrir_docx(chemin)
    onglets: list[Onglet] = []
    bloc: Bloc | None = None
    ouverts: dict[str, None] = {}  # commentaires en cours (ordonnés), leur plage peut couvrir plusieurs paragraphes

    def clore_bloc():
        nonlocal bloc
        if bloc is not None and onglets:
            onglets[-1].blocs.append(bloc)
        bloc = None

    for p in document.iter(W + "p"):
        style = p.find(f"{W}pPr/{W}pStyle")
        style = style.get(W + "val") if style is not None else ""
        morceaux, barres, total, commentes = [], 0, 0, {}
        for el in p.iter():
            if el.tag == W + "commentRangeStart":
                ouverts[el.get(W + "id")] = None
            elif el.tag == W + "commentRangeEnd":
                ouverts.pop(el.get(W + "id"), None)
            elif el.tag == W + "r":
                texte = "".join(n.text or "" if n.tag == W + "t" else " " if n.tag == W + "tab" else "\n"
                                for n in el if n.tag in (W + "t", W + "tab", W + "br", W + "cr"))
                morceaux.append(texte)
                n = len("".join(texte.split()))
                total += n
                if _actif(el.find(W + "rPr"), "strike") or _actif(el.find(W + "rPr"), "dstrike"):
                    barres += n
                if n:
                    commentes.update(ouverts)
        texte = "".join(morceaux)

        if style in STYLES_ONGLET:
            clore_bloc()
            onglets.append(Onglet(" ".join(texte.split())))
            continue
        if not texte.strip():
            clore_bloc()
            continue
        if not onglets:
            onglets.append(Onglet(""))  # contenu avant le premier onglet
        if bloc is None:
            bloc = Bloc()
        bloc.paragraphes.append(Paragraphe(
            lignes=[ligne for ligne in texte.split("\n") if ligne.strip()], barres=barres, total=total,
            commentaires=[textes_commentaires[i] for i in commentes if i in textes_commentaires]))
    clore_bloc()
    return onglets


# --- Du bloc à l'extrait ------------------------------------------------------

def _pages(m: re.Match) -> tuple[str, str]:
    debut, fin = m.group("debut"), m.group("fin") or ""
    if fin and len(fin) < len(debut):  # « p112-14 » veut dire 112 à 114
        fin = debut[:len(debut) - len(fin)] + fin
    return debut, "" if fin == debut else fin


def _marque_de_fin(ligne: str) -> re.Match | None:
    m = MARQUE_FIN.search(ligne)
    if not m:
        return None
    marque = m.group("m")
    if not marque.lstrip().startswith("(") and marque.rstrip().endswith(")"):
        # « (Ley, 2003, p. 12) », « (Dumas et Guillot, p. 2) » : la page d'un auteur cité
        # par le texte (une année, ou un nom suivi d'une virgule), pas celle du texte lu.
        ouvrante = ligne.rfind("(", 0, m.start())
        entre = ligne[ouvrante:m.start()] if ouvrante != -1 else ""
        if ANNEE.search(entre) or re.search(r"\w,\s*$", entre):
            return None
    return m


def _assembler(lignes: list[str]) -> str:
    """Recolle les lignes coupées par le PDF, garde les vrais retours à la ligne."""
    texte, precedente = "", ""
    for ligne in lignes:
        ligne = re.sub(r"[ \t]+", " ", ligne).strip()
        if not re.search(r"\w", ligne):  # ligne vide ou ponctuation égarée
            continue
        if not texte:
            texte = ligne
        elif re.search(r"[^\W\d_]-$", texte) and ligne[0].islower():
            texte = texte[:-1] + ligne  # mot coupé en fin de ligne : « multi- / plient »
        elif ((ligne[0].isupper() or ligne[0].isdigit() or ligne[0] in "-–•*→>")
              and (len(precedente) < 50 or precedente.endswith((".", ":", "!", "?")))):
            texte += "\n" + ligne  # liste ou nouvelle phrase après une ligne courte : vraie ligne
        else:
            texte += " " + ligne
        precedente = ligne
    return texte


def decouper(bloc: Bloc) -> list[Bloc]:
    """Coupe le bloc après chaque paragraphe qui finit par une page."""
    morceaux, courant = [], Bloc()
    for p in bloc.paragraphes:
        courant.paragraphes.append(p)
        if _marque_de_fin(p.lignes[-1]):
            morceaux.append(courant)
            courant = Bloc()
    if courant.paragraphes:
        morceaux.append(courant)
    return morceaux


def extrait_depuis_bloc(bloc: Bloc) -> ExtraitLu:
    lignes = bloc.lignes
    debut = fin = ""
    m = _marque_de_fin(lignes[-1])
    if m:
        debut, fin = _pages(m)
        lignes[-1] = lignes[-1][:m.start()].rstrip()
    else:
        m = MARQUE_DEBUT.match(lignes[0])
        if m:
            debut, fin = _pages(m)
            lignes[0] = lignes[0][m.end():].lstrip()
    barres = sum(p.barres for p in bloc.paragraphes)
    total = sum(p.total for p in bloc.paragraphes)
    return ExtraitLu(
        texte=_assembler(lignes),
        page_debut=debut,
        page_fin=fin,
        part_barree=barres / total if total else 0.0,
        commentaires=list(dict.fromkeys(c for p in bloc.paragraphes for c in p.commentaires)),
    )


def extraits_depuis_blocs(blocs: list[Bloc]) -> list[ExtraitLu]:
    extraits: list[ExtraitLu] = []
    for bloc in (morceau for b in blocs for morceau in decouper(b)):
        e = extrait_depuis_bloc(bloc)
        if e.texte:
            extraits.append(e)
        elif e.page_debut and extraits and not extraits[-1].page_debut:
            # Une page seule sur sa ligne, après une ligne vide : elle ferme le bloc précédent.
            extraits[-1].page_debut, extraits[-1].page_fin = e.page_debut, e.page_fin
    return extraits


# --- Analyse du document --------------------------------------------------------

def analyser(chemin: Path) -> list[OngletLu]:
    onglets = lire_onglets(chemin)
    if not any(o.titre for o in onglets):
        raise DonneesInvalides(
            "Aucun onglet trouvé dans ce document. L'import attend l'export Word du Google Doc "
            "d'extraits, où chaque onglet commence par son nom en style « Titre ».")
    lus, theme = [], None
    for i, o in enumerate(onglets):
        if not o.titre:
            continue
        if not o.blocs:
            # Onglet vide : un thème s'il est suivi d'onglets remplis ; sinon un
            # simple conteneur (« Littérature », au-dessus des thèmes).
            if i + 1 < len(onglets) and onglets[i + 1].blocs:
                theme = o.titre
            continue
        extraits = extraits_depuis_blocs(o.blocs)
        if not extraits:
            continue
        propose = theme is not None and not ONGLETS_HORS_LECTURE.match(o.titre)
        lus.append(OngletLu(o.titre, theme, propose, extraits))
    return lus


def source_depuis_onglet(titre: str) -> tuple[list[dict], str, str]:
    """(auteurs, année, titre) déduits du nom d'onglet : « Zanetti2022: En Europe »,
    « Pinel 2017 », « Arrieta: Garden led… ». Seul un nom d'un seul mot est pris
    pour un auteur : « Jardin de la rue Haute » n'en est pas un."""
    avant, deux_points, apres = titre.partition(":")
    annee = ANNEE.search(avant)
    nom = avant[:annee.start()] if annee else avant
    reste = avant[annee.end():] if annee else ""
    nom = nom.strip(" .,-")
    if (deux_points or annee) and re.fullmatch(r"[^\W\d_][\w'’-]*", nom):
        auteurs = [{"nom": nom.capitalize() if nom.isupper() else nom, "prenom": ""}]
        titre_source = apres.strip() if deux_points else reste.strip(" .,-:")
        return auteurs, annee.group() if annee else "", titre_source
    return [], annee.group() if annee else "", titre


# --- Import dans le mémoire -----------------------------------------------------

def _source_importee(memoire: Memoire, onglet: str) -> Source | None:
    for s in memoire.sources.values():
        if (s.origine_import or {}).get("onglet") == onglet:
            return s
    return None


def _mot_cle_existant(memoire: Memoire, theme: str) -> MotCle | None:
    # D'abord celui créé par un import précédent, même renommé depuis ;
    # sinon un mot-clé saisi à la main qui porte déjà ce nom.
    for m in memoire.mots_cles.values():
        if (m.origine_import or {}).get("onglet") == theme:
            return m
    for m in memoire.mots_cles.values():
        if theme.casefold() in {t.casefold() for t in [m.libelle, *m.synonymes]}:
            return m
    return None


def _empreintes(memoire: Memoire, source_id: str) -> set[str]:
    return {(e.origine_import or {}).get("empreinte") for e in memoire.extraits_de(source_id)}


def apercu(memoire: Memoire, chemin: Path) -> dict:
    """Ce que l'import ferait, sans rien écrire : l'utilisateur valide avant."""
    lus = analyser(chemin)
    onglets = []
    for o in lus:
        source = _source_importee(memoire, o.titre)
        deja = _empreintes(memoire, source.id) if source else set()
        auteurs, annee, _ = source_depuis_onglet(o.titre)
        onglets.append({
            "titre": o.titre,
            "theme": o.theme,
            "propose": o.propose,
            "auteur": auteurs[0]["nom"] if auteurs else "",
            "annee": annee,
            "extraits": len(o.extraits),
            "nouveaux": sum(e.empreinte not in deja for e in o.extraits),
            "integres": sum(e.integre for e in o.extraits),
            "avec_page": sum(bool(e.page_debut) for e in o.extraits),
            "deja_importe": source is not None,
            "exemple": o.extraits[0].texte[:220],
        })
    return {"document": Path(chemin).name, "onglets": onglets}


def importer(memoire: Memoire, chemin: Path, onglets: list[str] | None = None) -> dict:
    """Importe les onglets choisis (par défaut : ceux proposés par l'aperçu)."""
    chemin = Path(chemin)
    lus = analyser(chemin)
    choisis = set(onglets) if onglets is not None else {o.titre for o in lus if o.propose}

    nouveaux_mots: dict[str, MotCle] = {}
    couleurs_prises = {m.couleur for m in memoire.mots_cles.values() if not m.parent_id}
    nouvelles_sources: list[Source] = []
    nouveaux_extraits: list[Extrait] = []
    rapport = {"sources_creees": 0, "sources_completees": 0, "extraits_crees": 0, "extraits_deja_la": 0,
               "integres": 0, "a_verifier": 0, "sans_page": 0, "mots_cles_crees": []}

    for o in lus:
        if o.titre not in choisis:
            continue
        mot = None
        if o.theme:
            mot = nouveaux_mots.get(o.theme) or _mot_cle_existant(memoire, o.theme)
            if mot is None:
                couleur = next((c for c in PALETTE if c not in couleurs_prises), PALETTE[len(couleurs_prises) % len(PALETTE)])
                couleurs_prises.add(couleur)
                mot = MotCle(libelle=o.theme, couleur=couleur, origine_import={"onglet": o.theme})
                nouveaux_mots[o.theme] = mot
                rapport["mots_cles_crees"].append(o.theme)

        source = _source_importee(memoire, o.titre)
        if source is None:
            auteurs, annee, titre = source_depuis_onglet(o.titre)
            source = Source(type="article_revue", auteurs=auteurs, annee=annee, titre=titre, statut="fiche",
                            provenance="import_extraits",
                            origine_import={"document": chemin.name, "onglet": o.titre})
            nouvelles_sources.append(source)
            rapport["sources_creees"] += 1
            deja = set()
        else:
            deja = _empreintes(memoire, source.id)

        ajoutes = 0
        for lu in o.extraits:
            if lu.empreinte in deja:
                rapport["extraits_deja_la"] += 1
                continue
            deja.add(lu.empreinte)  # deux blocs identiques dans l'onglet : un seul extrait
            note = []
            if lu.commentaires:
                note.append("Commentaire dans le Google Doc : " + " / ".join(lu.commentaires))
            if lu.barre_en_partie:
                note.append(f"Import : passage barré en partie seulement ({round(lu.part_barree * 100)} %) "
                            f"dans le Google Doc. Vérifie la case « intégré ».")
                rapport["a_verifier"] += 1
            nouveaux_extraits.append(Extrait(
                source_id=source.id,
                texte=lu.texte,
                page_debut=lu.page_debut,
                page_fin=lu.page_fin,
                nature="citation" if lu.page_debut else "paraphrase",
                mots_cles=[mot.id] if mot else [],
                integre=lu.integre,
                note="\n".join(note),
                origine_import={"document": chemin.name, "onglet": o.titre, "empreinte": lu.empreinte},
            ))
            ajoutes += 1
            rapport["integres"] += lu.integre
            rapport["sans_page"] += not lu.page_debut
        rapport["extraits_crees"] += ajoutes
        if ajoutes and source not in nouvelles_sources:
            rapport["sources_completees"] += 1

    if nouveaux_mots or nouvelles_sources or nouveaux_extraits:
        memoire.ajouter_en_lot(list(nouveaux_mots.values()), nouvelles_sources, nouveaux_extraits)
    return rapport
