"""Mise en forme APA 7 : références, citations dans le texte, bibliographie.

Sources des règles, par ordre de priorité :
1. « Recommandations pour la présentation des références bibliographiques »,
   Bibliothèques de l'ULB, V10, 05/02/2024 : article, livre, thèse, chapitre,
   page web, citations dans le texte, ordre des notices ;
2. Guide du Master 2025-2026 : bibliographie en trois parties, date de
   consultation des sites ;
3. APA 7 dans son adaptation française (« et », « s. d. », « (dir.) »), pour
   les types que le guide ULB ne couvre pas : communication de colloque,
   support de cours, rapport, presse, audiovisuel ;
4. textes légaux et jurisprudence belges, que ni APA ni l'ULB ne couvrent :
   la forme déjà employée dans la bibliographie de la première partie.

Chaque référence est rendue en segments (texte, italique ?) : la même mise en
forme donne le HTML pour Google Docs (italique conservé) et le texte brut.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field

from .modele import ReglagesAPA, Source

# --- Champs par type ------------------------------------------------------------


@dataclass(frozen=True)
class Champ:
    cle: str
    libelle: str  # vocabulaire courant, pas de jargon
    obligatoire: bool = False
    genre: str = "texte"  # texte | personnes | case


LIBELLES_TYPES = {
    "article_revue": "Article de revue", "livre": "Livre", "chapitre": "Chapitre d'ouvrage collectif",
    "article_presse": "Article de presse", "rapport": "Rapport", "memoire_these": "Mémoire ou thèse",
    "page_web": "Page web", "communication_colloque": "Communication de colloque",
    "support_cours": "Support de cours", "document_institutionnel": "Catalogue, dossier de presse…",
    "audiovisuel": "Vidéo, podcast, conférence", "texte_legal": "Texte légal", "jurisprudence": "Jurisprudence",
    "communication_personnelle": "Entretien, échange personnel",
}

_DOI = Champ("doi", "DOI (s'il y en a un)")
_URL = Champ("url", "Adresse web")
_DATE = Champ("date_precise", "Jour et mois (ex. 20 mai)")
# Pas imprimé dans la référence APA : sert à retrouver le livre (et, si l'utilisateur l'autorise, à le compléter).
_ISBN = Champ("isbn", "ISBN (au dos du livre)")

CHAMPS: dict[str, tuple[Champ, ...]] = {
    "livre": (Champ("dirige", "Ouvrage dirigé (les auteurs sont les directeurs)", genre="case"),
              Champ("edition", "Édition, si ce n'est pas la première (ex. 2e)"),
              Champ("volume", "Volume"), Champ("editeur", "Éditeur", obligatoire=True), _DOI, _ISBN, _URL),
    "chapitre": (Champ("directeurs", "Qui a dirigé l'ouvrage ?", obligatoire=True, genre="personnes"),
                 Champ("titre_ouvrage", "Titre de l'ouvrage collectif", obligatoire=True),
                 Champ("edition", "Édition, si ce n'est pas la première"), Champ("volume", "Volume"),
                 Champ("pages", "Pages du chapitre (ex. 29-43)", obligatoire=True),
                 Champ("editeur", "Éditeur", obligatoire=True), _DOI, _ISBN, _URL),
    "article_revue": (Champ("revue", "Dans quelle revue ?", obligatoire=True), Champ("volume", "Volume"),
                      Champ("numero", "Numéro"), Champ("pages", "Pages (ex. 137-161)"), _DOI, _URL),
    "article_presse": (_DATE, Champ("journal", "Dans quel journal ou magazine ?", obligatoire=True),
                       Champ("pages", "Pages"), _URL),
    "rapport": (Champ("numero", "Numéro du rapport"), Champ("editeur", "Publié par (si ce n'est pas l'auteur)"),
                _DOI, _URL),
    "texte_legal": (_DATE, Champ("precision", "Précision (ex. Version consolidée)"),
                    Champ("publication", "Où est-il publié ? (ex. Moniteur belge)"), _URL),
    "jurisprudence": (_DATE, Champ("precision", "Objet de l'affaire"), _URL),
    "page_web": (_DATE, Champ("site", "Nom du site"),
                 Champ("url", "Adresse web", obligatoire=True),
                 Champ("consulte_le", "Consulté le (ex. 29 septembre 2026)", obligatoire=True)),
    "memoire_these": (Champ("nature", "Mémoire ou thèse ? (ex. Thèse de doctorat)", obligatoire=True),
                      Champ("institution", "Université", obligatoire=True), _URL),
    "document_institutionnel": (Champ("nature", "De quoi s'agit-il ? (ex. Dossier de presse)"),
                                Champ("editeur", "Publié par (si ce n'est pas l'auteur)"), _URL),
    "audiovisuel": (_DATE, Champ("nature", "Format (ex. Vidéo, Podcast)", obligatoire=True),
                    Champ("plateforme", "Où ? (ex. YouTube, chaîne, radio)"), _URL),
    "communication_colloque": (_DATE, Champ("evenement", "Nom du colloque", obligatoire=True),
                               Champ("lieu", "Lieu ou organisateur"), _URL),
    "support_cours": (Champ("nature", "Nature (ex. Syllabus, Notes de cours)", obligatoire=True),
                      Champ("institution", "Université", obligatoire=True), _URL),
    "communication_personnelle": (_DATE, Champ("nature", "Nature (ex. entretien, courriel)")),
}

# Bibliographie en trois parties (Guide du Master, p. 24).
SECTIONS = (
    ("scientifique", "Références bibliographiques"),
    ("non_scientifique", "Sources non scientifiques"),
    ("sitographie", "Sitographie"),
)
SECTION_DU_TYPE = {
    "livre": "scientifique", "chapitre": "scientifique", "article_revue": "scientifique",
    "memoire_these": "scientifique", "communication_colloque": "scientifique", "support_cours": "scientifique",
    "article_presse": "non_scientifique", "rapport": "non_scientifique", "texte_legal": "non_scientifique",
    "jurisprudence": "non_scientifique", "document_institutionnel": "non_scientifique",
    "audiovisuel": "non_scientifique",
    "page_web": "sitographie",
}

# Titre en italique : l'œuvre se tient seule. Sinon c'est son contenant
# (revue, journal, ouvrage collectif) qui est en italique.
TITRE_ITALIQUE = {"livre", "memoire_these", "rapport", "texte_legal", "jurisprudence", "page_web",
                  "document_institutionnel", "audiovisuel", "communication_colloque", "support_cours"}


# --- Texte mis en forme ------------------------------------------------------------

@dataclass
class Mise:
    """Texte fait de segments (texte, italique)."""

    segments: list[tuple[str, bool]] = field(default_factory=list)
    manques: list[str] = field(default_factory=list)  # champs à compléter

    def ajouter(self, texte: str, italique: bool = False) -> Mise:
        if texte:
            if self.segments and self.segments[-1][1] == italique:
                self.segments[-1] = (self.segments[-1][0] + texte, italique)
            else:
                self.segments.append((texte, italique))
        return self

    def etendre(self, autre: Mise) -> Mise:
        for texte, italique in autre.segments:
            self.ajouter(texte, italique)
        return self

    @property
    def texte(self) -> str:
        return "".join(t for t, _ in self.segments)

    @property
    def html(self) -> str:
        return "".join(f"<i>{html.escape(t, quote=False)}</i>" if i else html.escape(t, quote=False)
                       for t, i in self.segments)

    def finit_par(self, caracteres: str) -> bool:
        return self.texte.rstrip().endswith(tuple(caracteres))


def _point(mise: Mise) -> Mise:
    """Termine l'élément par un point, sauf s'il finit déjà par . ? ou !"""
    if not mise.finit_par(".?!"):
        mise.ajouter(".")
    return mise


# --- Petits formats ---------------------------------------------------------------

def _tiret(texte: str) -> str:
    # Traits d'union insécables et tirets copiés des PDF : un trait simple, comme le guide ULB.
    return re.sub(r"\s*[‐‑‒–—]\s*", "-", str(texte).strip())


def initiales(prenom: str) -> str:
    """« Cara Gendel » → « C. G. » ; « Jean-Pierre » → « J.-P. » ; « Ch. » reste « Ch. »."""
    morceaux = []
    for mot in prenom.split():
        parties = [p for p in mot.split("-") if p]
        morceaux.append("-".join(p if p.endswith(".") else p[0].upper() + "." for p in parties))
    return " ".join(morceaux)


def doi_en_url(doi: str) -> str:
    doi = str(doi).strip()
    m = re.search(r"10\.\d{4,9}/\S+", doi)
    return f"https://doi.org/{m.group()}" if m else doi


def _nom(auteur: dict) -> str:
    return (auteur.get("organisation") or auteur.get("nom") or "").strip()


def _auteur_reference(auteur: dict) -> str:
    if auteur.get("organisation"):
        return auteur["organisation"].strip()
    prenom = initiales(auteur.get("prenom", ""))
    return f"{auteur['nom'].strip()}, {prenom}" if prenom else auteur["nom"].strip()


def _enumerer(noms: list[str], conjonction: str) -> str:
    if len(noms) <= 1:
        return "".join(noms)
    if conjonction == "&":  # usage anglais : virgule avant l'esperluette
        return ", ".join(noms[:-1]) + ", & " + noms[-1]
    return ", ".join(noms[:-1]) + f" {conjonction} " + noms[-1]


def auteurs_reference(auteurs: list[dict], conjonction: str) -> str:
    noms = [_auteur_reference(a) for a in auteurs if _nom(a)]
    if len(noms) > 20:  # guide ULB : les 19 premiers, « . . . », puis le dernier
        return ", ".join(noms[:19]) + ", . . . " + noms[-1]
    return _enumerer(noms, conjonction)


def _directeurs(personnes: list[dict], r: ReglagesAPA) -> str:
    noms = []
    for p in personnes:
        if p.get("organisation"):
            noms.append(p["organisation"].strip())
        elif _nom(p):
            prenom = initiales(p.get("prenom", ""))
            noms.append(f"{prenom} {p['nom'].strip()}".strip())
    mention = r.directeurs if len(noms) > 1 else r.directeur
    return f"{_enumerer(noms, r.conjonction)} {mention}"


def annee_affichee(source: Source, r: ReglagesAPA, suffixe: str = "") -> str:
    annee = str(source.annee).strip()
    if not annee:
        return r.sans_date + (f"-{suffixe}" if suffixe else "")
    return annee + suffixe


def _pages(debut: str, fin: str, r: ReglagesAPA) -> str:
    debut, fin = str(debut or "").strip(), str(fin or "").strip()
    if fin and fin != debut:
        return f"{r.pages} {debut}-{fin}"
    return f"{r.page} {debut}" if debut else ""


def _majuscule(texte: str) -> str:
    return texte[:1].upper() + texte[1:]


# --- Référence complète --------------------------------------------------------------

def _manques(source: Source) -> list[str]:
    manques = []
    if not source.titre.strip():
        manques.append("titre")
    for c in CHAMPS.get(source.type, ()):
        if c.obligatoire and not source.champs.get(c.cle):
            manques.append(c.libelle)
    return manques


def reference(source: Source, r: ReglagesAPA, suffixe: str = "") -> Mise | None:
    """Référence pour la bibliographie. None pour une communication personnelle,
    qui n'est citée que dans le texte."""
    if source.type == "communication_personnelle":
        return None
    c = {k: (_tiret(v) if k in ("pages", "volume", "numero") else v) for k, v in source.champs.items()}
    italique = source.type in TITRE_ITALIQUE
    m = Mise(manques=_manques(source))

    titre = Mise().ajouter(source.titre.strip(), italique)
    if source.type == "livre":
        details = [f"{c['edition']} éd." if c.get("edition") else "", f"vol. {c['volume']}" if c.get("volume") else ""]
        if any(details):
            titre.ajouter(" (" + ", ".join(d for d in details if d) + ")")
    precision = c.get("nature") if source.type in ("memoire_these", "document_institutionnel", "audiovisuel",
                                                    "support_cours") else c.get("precision")
    if source.type == "communication_colloque":
        precision = "Communication"
    if precision:
        titre.ajouter(f" [{precision}]")

    date = annee_affichee(source, r, suffixe)
    if c.get("date_precise") and source.type in ("article_presse", "texte_legal", "jurisprudence", "page_web",
                                                 "audiovisuel", "communication_colloque"):
        date += f", {c['date_precise'].strip()}"

    # Auteur, date, titre. Sans auteur, le titre prend la place de l'auteur (APA).
    auteurs = auteurs_reference(source.auteurs, r.conjonction)
    if auteurs:
        m.ajouter(auteurs)
        if source.type == "livre" and c.get("dirige"):
            m.ajouter(f" {r.directeurs if len(source.auteurs) > 1 else r.directeur}")
        _point(m).ajouter(f" ({date}). ")
        m.etendre(_point(titre))
    else:
        m.etendre(_point(titre)).ajouter(f" ({date}).")

    suite = Mise()
    t = source.type
    if t == "chapitre":
        if c.get("directeurs"):
            suite.ajouter(f"Dans {_directeurs(c['directeurs'], r)}, ")
        suite.ajouter(c.get("titre_ouvrage", "").strip(), True)
        details = [f"{c['edition']} éd." if c.get("edition") else "", f"vol. {c['volume']}" if c.get("volume") else "",
                   f"{r.pages if '-' in c.get('pages', '') else r.page} {c['pages']}" if c.get("pages") else ""]
        if any(details):
            suite.ajouter(" (" + ", ".join(d for d in details if d) + ")")
        _point(suite)
        if c.get("editeur"):
            suite.ajouter(f" {c['editeur'].strip()}.")
    elif t == "article_revue":
        revue = c.get("revue", "").strip()
        if c.get("volume"):
            suite.ajouter(f"{revue}, {c['volume']}", True)
        else:
            suite.ajouter(revue, True)
            if c.get("numero"):
                suite.ajouter(",")
        if c.get("numero"):
            suite.ajouter(f"{'' if c.get('volume') else ' '}({c['numero']})")
        if c.get("pages"):
            suite.ajouter(f", {c['pages']}")
        _point(suite)
    elif t == "article_presse":
        suite.ajouter(c.get("journal", "").strip(), True)
        if c.get("pages"):
            suite.ajouter(f", {c['pages']}")
        _point(suite)
    elif t in ("rapport", "document_institutionnel", "livre"):
        editeur = c.get("editeur", "").strip()
        if editeur and editeur != auteurs:
            suite.ajouter(f"{editeur}.")
    elif t == "texte_legal":
        if c.get("publication"):
            suite.ajouter(f"{c['publication'].strip()}.")
    elif t == "page_web":
        site = c.get("site", "").strip()
        if site and site != auteurs:
            suite.ajouter(f"{site}.")
    elif t in ("memoire_these", "support_cours"):
        if c.get("institution"):
            suite.ajouter(f"{c['institution'].strip()}.")
    elif t == "audiovisuel":
        if c.get("plateforme"):
            suite.ajouter(f"{c['plateforme'].strip()}.")
    elif t == "communication_colloque":
        lieu = ", ".join(x.strip() for x in (c.get("evenement", ""), c.get("lieu", "")) if x and x.strip())
        if lieu:
            suite.ajouter(f"{lieu}.")
    if suite.segments:
        m.ajouter(" ").etendre(suite)

    lien = doi_en_url(c["doi"]) if c.get("doi") else (c.get("url") or "").strip()
    if t == "page_web" and c.get("consulte_le"):
        # Forme APA de la date de consultation selon Boussole (ULB) : « Consulté le [date] de [URL] ».
        m.ajouter(f" {_majuscule(r.consulte_le)} {c['consulte_le'].strip()}" + (f" de {lien}" if lien else "."))
    elif lien:
        m.ajouter(f" {lien}")
    return m


# --- Citation dans le texte ------------------------------------------------------------

def _qui(auteurs: list[dict], titre: str, type_: str, conjonction: str, initiales_premier: bool = False) -> Mise:
    noms = [_nom(a) for a in auteurs if _nom(a)]
    if not noms:  # sans auteur : le titre, en italique s'il l'est dans la référence
        return Mise().ajouter(titre.strip(), type_ in TITRE_ITALIQUE)
    premier = next(a for a in auteurs if _nom(a))
    if initiales_premier and premier.get("prenom", "").strip() and not premier.get("organisation"):
        noms[0] = f"{initiales(premier['prenom'])} {noms[0]}"  # APA 7 § 8.20 : (J. Martin, 2020)
    if len(noms) >= 3:
        return Mise().ajouter(f"{noms[0]} et al.")
    return Mise().ajouter(_enumerer(noms, conjonction).replace(", &", " &"))


def citation(source: Source, r: ReglagesAPA, *, page_debut: str = "", page_fin: str = "", suffixe: str = "",
             auteur_origine: dict | None = None, narrative: bool = False, avec_initiales: bool = False) -> Mise:
    """(Martin, 2020, p. 45) ou Martin (2020, p. 45).

    Avec `auteur_origine` (source secondaire) : (Piaget, 1952, cité dans Martin, 2020, p. 45).
    « et » dans la forme narrative même si « & » est choisi : on écrit une phrase en français.
    `avec_initiales` : le premier auteur a un homonyme parmi les sources (voir homonymes()).
    """
    if source.type == "communication_personnelle":
        qui = " ".join(filter(None, (initiales(source.auteurs[0].get("prenom", "")) if source.auteurs else "",
                                     _nom(source.auteurs[0]) if source.auteurs else "")))
        quand = source.champs.get("date_precise", "").strip()
        quand = f"{quand} {source.annee}".strip() if source.annee else quand
        detail = ", ".join(filter(None, ("communication personnelle", quand)))
        return Mise().ajouter(f"{qui} ({detail})" if narrative else f"({qui}, {detail})")

    lue = _qui(source.auteurs, source.titre, source.type, "et" if narrative else r.conjonction, avec_initiales)
    fin = ", ".join(filter(None, (annee_affichee(source, r, suffixe), _pages(page_debut, page_fin, r))))
    m = Mise()
    if auteur_origine:
        origine = _qui(auteur_origine.get("auteurs", []), "", "", "et" if narrative else r.conjonction)
        annee_origine = str(auteur_origine.get("annee") or "").strip() or r.sans_date
        if narrative:
            m.etendre(origine).ajouter(f" ({annee_origine}, {r.cite_dans} ").etendre(lue).ajouter(f", {fin})")
        else:
            m.ajouter("(").etendre(origine).ajouter(f", {annee_origine}, {r.cite_dans} ").etendre(lue).ajouter(f", {fin})")
        return m
    if narrative:
        return m.etendre(lue).ajouter(f" ({fin})")
    return m.ajouter("(").etendre(lue).ajouter(f", {fin})")


def etiquette(source: Source, r: ReglagesAPA, suffixe: str = "", avec_initiales: bool = False) -> str:
    """« Hartmann et Keller (1984) » : la forme sous laquelle on pense à une source, dans les listes."""
    if not source.auteurs and not source.titre.strip():
        return "Source sans auteur ni titre"
    return citation(source, r, suffixe=suffixe, narrative=True, avec_initiales=avec_initiales).texte


def citation_litterale(texte: str, source: Source, r: ReglagesAPA, **options) -> Mise:
    """« texte copié » (Martin, 2020, p. 45) : guillemets français, espaces insécables."""
    texte = texte.strip().strip("«»\"“”").strip()
    return Mise().ajouter(f"« {texte} » ").etendre(citation(source, r, **options))


# --- Même auteur, même année ; bibliographie ---------------------------------------------

def _cle_tri(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFD", texte)
    return "".join(ch for ch in sans_accents if not unicodedata.combining(ch)).casefold()


def _cle_auteurs(source: Source) -> tuple:
    """Nom puis initiales de chaque auteur : J. Martin et P. Martin sont deux personnes
    (pas de lettres a/b entre eux ; J. avant P. dans la bibliographie, APA 7 § 9.46)."""
    return (tuple((_cle_tri(_nom(a)), _cle_tri(initiales(a.get("prenom", "")) if not a.get("organisation") else ""))
                  for a in source.auteurs if _nom(a))
            or ((_cle_tri(source.titre), ""),))


def homonymes(sources: list[Source]) -> set[str]:
    """Sources dont le premier auteur partage son nom avec le premier auteur d'une autre
    source, avec d'autres initiales : leurs citations portent les initiales (J. Martin, 2020).
    Un prénom absent ne compte pas comme une autre personne."""
    par_nom: dict[str, dict[str, list[str]]] = {}
    for s in sources:
        premier = next((a for a in s.auteurs if _nom(a)), None)
        if s.type == "communication_personnelle" or not premier or premier.get("organisation"):
            continue
        ini = _cle_tri(initiales(premier.get("prenom", "")))
        if ini:
            par_nom.setdefault(_cle_tri(_nom(premier)), {}).setdefault(ini, []).append(s.id)
    return {i for groupes in par_nom.values() if len(groupes) > 1 for ids in groupes.values() for i in ids}


def suffixes(sources: list[Source]) -> dict[str, str]:
    """Lettres a, b, c… pour les mêmes auteurs la même année, par ordre alphabétique des titres."""
    groupes: dict[tuple, list[Source]] = {}
    for s in sources:
        if s.type != "communication_personnelle":
            groupes.setdefault((_cle_auteurs(s), str(s.annee).strip()), []).append(s)
    lettres = {}
    for groupe in groupes.values():
        if len(groupe) > 1:
            for i, s in enumerate(sorted(groupe, key=lambda s: _cle_tri(s.titre))):
                lettres[s.id] = "abcdefghijklmnopqrstuvwxyz"[i]
    return lettres


def bibliographie(sources: list[Source], r: ReglagesAPA, lettres: dict[str, str] | None = None,
                  decoupage: str = "une_liste") -> list[tuple[str, list[tuple[Source, Mise]]]]:
    """Références triées (premier auteur, auteurs suivants, année) : une seule liste
    « Références » comme le veut l'APA, ou, avec `decoupage="trois_parties"`, réparties
    comme le demande par exemple le Guide du Master de l'ULB. Parties vides omises.

    `lettres` : les a/b calculés sur toutes les sources, pour que la bibliographie
    porte les mêmes lettres que les citations déjà collées dans le texte."""
    lettres = suffixes(sources) if lettres is None else lettres

    def tri(s: Source):
        annee = str(s.annee).strip()
        # Sans date avant les dates (usage APA), puis a, b… déjà dans l'ordre des titres.
        return (_cle_auteurs(s), annee != "", annee, lettres.get(s.id, ""), _cle_tri(s.titre))

    avec_reference = [s for s in sources if s.type in SECTION_DU_TYPE]  # pas les communications personnelles
    if decoupage == "une_liste":
        membres = sorted(avec_reference, key=tri)
        return [("Références", [(s, reference(s, r, lettres.get(s.id, ""))) for s in membres])] if membres else []
    parties = []
    for cle, titre in SECTIONS:
        membres = sorted((s for s in avec_reference if SECTION_DU_TYPE[s.type] == cle), key=tri)
        if membres:
            parties.append((titre, [(s, reference(s, r, lettres.get(s.id, ""))) for s in membres]))
    return parties
