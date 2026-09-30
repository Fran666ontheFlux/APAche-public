"""Import des PDF des dossiers « à lire » et « lus » (par ex. « Articles à lire », « Articles LUS »).

Les deux dossiers recoupent le statut des sources : à lire, lu. Chaque fichier
est proposé à l'utilisateur, un par un : le joindre à une source déjà là (celle
de l'onglet du Google Doc, par exemple), créer une source, ou passer.

Les fichiers de l'utilisateur ne sont jamais déplacés ni renommés : ils sont
copiés dans le dossier de données, comme un fichier glissé dans une fiche. Une
copie plutôt qu'un lien, parce que le chemin du Drive diffère d'un PC à l'autre.
Un fichier est reconnu à son contenu (empreinte) : l'import se rejoue sans
doublon, même si le fichier a été renommé entre-temps.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import apa, fichiers
from .depot import Memoire
from .modele import DonneesInvalides, Source

EXTENSIONS = (".pdf", ".docx")
SEUIL_NOM = 0.8
ANNEE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
DOI = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
# Titres de métadonnées sans valeur : ceux que Word ou un scanner mettent d'office.
TITRE_VIDE = re.compile(r"^(untitled|sans titre|document\d*|microsoft word|scan|\d+)\b|\.(docx?|pdf|indd)$", re.IGNORECASE)

_analyses: dict[str, list[FichierTrouve]] = {}  # dossier analysé → fichiers, pour appliquer sans tout relire


@dataclass
class FichierTrouve:
    chemin: Path
    relatif: str          # depuis le dossier choisi, pour l'affichage
    dossier: str          # « Articles à lire »…
    statut: str           # a_lire | lu
    empreinte: str


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if not unicodedata.combining(c)).casefold()


def statut_du_dossier(nom: str) -> str | None:
    """« Articles à lire » → a_lire ; « Articles LUS », « Lu » → lu ; le reste n'est pas importé."""
    mots = re.findall(r"[a-z]+", _sans_accents(nom))
    if "lire" in mots:
        return "a_lire"
    if "lu" in mots or "lus" in mots:
        return "lu"
    return None


def _empreinte(chemin: Path) -> str:
    h = hashlib.sha1()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()[:20]


def parcourir(racine: Path) -> tuple[list[FichierTrouve], list[str]]:
    """Les fichiers des dossiers « à lire » et « lus », et les noms des dossiers laissés de côté."""
    racine = Path(racine)
    if not racine.is_dir():
        raise DonneesInvalides(f"Le dossier « {racine} » est introuvable. Vérifie le chemin, et que ton dossier "
                               f"synchronisé (Google Drive, OneDrive…) est disponible.")
    propre = statut_du_dossier(racine.name)
    dossiers = [(racine, propre)] if propre else [(d, statut_du_dossier(d.name)) for d in sorted(racine.iterdir()) if d.is_dir()]
    ignores = [d.name for d, statut in dossiers if not statut]
    trouves = []
    for dossier, statut in dossiers:
        if not statut:
            continue
        for chemin in sorted(dossier.rglob("*")):
            if chemin.is_file() and chemin.suffix.lower() in EXTENSIONS and not chemin.name.startswith(("~$", ".")):
                trouves.append(FichierTrouve(chemin, str(chemin.relative_to(racine)), dossier.name, statut, _empreinte(chemin)))
    if not trouves and not propre and not any(s for _, s in dossiers):
        raise DonneesInvalides("Aucun dossier « à lire » ou « lus » ici (par ex. « Articles à lire », « Articles lus »). "
                               "Indique le dossier qui les contient, ou directement l'un des deux.")
    return trouves, ignores


# --- Ce que le fichier dit de lui-même ---------------------------------------------

def _metadonnees(chemin: Path) -> tuple[str, str, str]:
    """(titre, auteur, début du texte) ; vides si le fichier ne les donne pas."""
    if chemin.suffix.lower() != ".pdf":
        try:
            texte = fichiers.texte_du_fichier(chemin)["pages"][0]["texte"]
        except DonneesInvalides:
            texte = ""
        return "", "", texte[:1500]
    try:
        from pypdf import PdfReader

        lecteur = PdfReader(str(chemin))
        infos = lecteur.metadata or {}
        texte = (lecteur.pages[0].extract_text() or "") if lecteur.pages else ""
        return str(infos.get("/Title") or "").strip(), str(infos.get("/Author") or "").strip(), texte[:1500]
    except Exception:  # un PDF illisible reste importable : on le joint, on le lira à la main
        return "", "", ""


def auteurs_des_metadonnees(texte: str) -> list[dict]:
    """/Author d'un PDF. « Tom Slater ; Loretta Lees », « Tom Slater and Loretta Lees »,
    « Tom Slater, Loretta Lees » : prénom puis nom. « Slater, Tom » : nom, virgule, prénom."""
    auteurs = []
    for groupe in re.split(r"\s*(?:;| and | et | & )\s*", texte.strip()):
        parties = [x.strip() for x in groupe.split(",") if x.strip()]
        if len(parties) == 2 and 1 in (len(parties[0].split()), len(parties[1].split())):
            # Une virgule, un des deux côtés en un mot : « Nom, Prénom » (l'usage des bibliothèques).
            auteurs.append({"nom": parties[0], "prenom": parties[1]})
            continue
        for morceau in parties:
            mots = morceau.split()
            if mots:
                auteurs.append({"nom": mots[-1], "prenom": " ".join(mots[:-1])})
    return auteurs


def proposition(f: FichierTrouve) -> dict:
    titre_meta, auteur_meta, debut = _metadonnees(f.chemin)
    nom = re.sub(r"[_]+", " ", f.chemin.stem).strip()
    annee = ANNEE.search(nom)
    doi = DOI.search(debut)
    auteurs = []
    if auteur_meta and not re.search(r"\d|user|admin|pc$", auteur_meta, re.IGNORECASE):
        auteurs = auteurs_des_metadonnees(auteur_meta)
    titre_nom = nom
    if not auteurs and annee:
        # « Arrieta 2017 - Garden led » : un seul mot avant l'année, c'est l'auteur.
        avant = nom[:annee.start()].strip(" -–—,.(")
        if re.fullmatch(r"[^\W\d_][\w'’-]*", avant):
            auteurs.append({"nom": avant, "prenom": ""})
            titre_nom = nom[annee.end():].strip(" -–—,.)") or nom
    elif not auteurs:
        # « Moretti - On the road » : un seul mot, un tiret, le titre.
        m = re.fullmatch(r"([^\W\d_][\w'’-]*)\s+[-–—]\s+(.+)", nom)
        if m:
            auteurs.append({"nom": m.group(1), "prenom": ""})
            titre_nom = m.group(2).strip()
    if titre_meta and not TITRE_VIDE.search(titre_meta) and len(titre_meta) > 5:
        titre = titre_meta
    else:
        titre = titre_nom
    return {"titre": titre, "auteurs": auteurs, "annee": annee.group() if annee else "",
            "doi": apa.doi_en_url(doi.group().rstrip(".,;)")) if doi else "", "debut": debut[:400]}


# --- Rapprochement -------------------------------------------------------------------

def _mots(texte: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", _sans_accents(texte)))


def candidats(memoire: Memoire, prop: dict, nom_fichier: str) -> list[dict]:
    """Sources sans fichier joint dont l'auteur, ou à défaut le titre, ressemble au fichier."""
    noms = {w for a in prop["auteurs"] for w in _mots(a.get("nom", ""))}
    mots_fichier = _mots(f"{nom_fichier} {prop['titre']}")
    trouves = []
    for s in memoire.sources.values():
        if s.fichier_joint:
            continue
        if s.annee and prop["annee"] and s.annee[:4] != prop["annee"][:4]:
            continue
        mots_source = {w for a in s.auteurs for w in _mots(a.get("nom") or a.get("organisation") or "")}
        # Du nom d'onglet, seulement le premier mot : l'auteur (« Mayer Compost Coll »).
        # Tous les mots feraient proposer « Arrieta: Garden Led… » pour n'importe quel PDF sur les jardins.
        premier = re.findall(r"[^\W\d_]+", (s.origine_import or {}).get("onglet", ""))
        mots_source |= _mots(premier[0]) if premier else set()
        # L'auteur trouvé dans le fichier, ou n'importe quel mot du nom de fichier (« Arrieta_jardins.pdf »).
        score = max((difflib.SequenceMatcher(None, a, b).ratio() for a in (noms or mots_fichier) for b in mots_source),
                    default=0)
        titre = _mots(s.titre)
        commun = len(titre & mots_fichier) / len(titre) if titre else 0
        if score >= SEUIL_NOM or commun >= 0.6:
            trouves.append((max(score, commun), s))
    trouves.sort(key=lambda x: -x[0])
    lettres = apa.suffixes(list(memoire.sources.values()))
    hom = apa.homonymes(list(memoire.sources.values()))
    r = memoire.projet.reglages_apa
    return [{"id": s.id, "etiquette": apa.etiquette(s, r, lettres.get(s.id, ""), s.id in hom),
             "titre": s.titre, "statut": s.statut, "nb_extraits": len(memoire.extraits_de(s.id))}
            for _, s in trouves[:5]]


def _deja(memoire: Memoire, empreinte: str) -> Source | None:
    return next((s for s in memoire.sources.values()
                 if (s.origine_import or {}).get("empreinte_fichier") == empreinte), None)


# --- Aperçu et application ------------------------------------------------------------

def apercu(memoire: Memoire, racine: Path) -> dict:
    trouves, ignores = parcourir(racine)
    _analyses[str(Path(racine).resolve())] = trouves
    resultat = []
    for f in trouves:
        deja = _deja(memoire, f.empreinte)
        prop = proposition(f) if not deja else {"titre": "", "auteurs": [], "annee": "", "doi": "", "debut": ""}
        debut = prop.pop("debut")
        resultat.append({
            "empreinte": f.empreinte, "nom": f.chemin.name, "relatif": f.relatif, "dossier": f.dossier,
            "statut": f.statut, "taille": f.chemin.stat().st_size, "proposition": prop,
            "debut": debut,
            "candidats": [] if deja else candidats(memoire, prop, f.chemin.stem),
            "deja": {"id": deja.id} if deja else None,
        })
    return {"fichiers": resultat, "ignores": ignores,
            "dossiers": sorted({(f.dossier, f.statut) for f in trouves})}


def appliquer(memoire: Memoire, racine: Path, empreinte: str, action: str, source_id: str | None = None) -> dict:
    cle = str(Path(racine).resolve())
    trouve = next((f for f in _analyses.get(cle) or parcourir(racine)[0] if f.empreinte == empreinte), None)
    if trouve is None or not trouve.chemin.exists():
        raise DonneesInvalides("Ce fichier n'est plus dans le dossier (déplacé ou supprimé ?) : relance l'analyse.")
    if _empreinte(trouve.chemin) != empreinte:
        raise DonneesInvalides("Ce fichier a changé depuis l'analyse : relance l'analyse.")
    if _deja(memoire, empreinte):
        raise DonneesInvalides("Ce fichier a déjà été importé.")
    origine = {"dossier": trouve.dossier, "fichier": trouve.relatif, "empreinte_fichier": empreinte}
    # Lire et vérifier le fichier avant de créer quoi que ce soit : un échec ne laisse
    # pas de source vide derrière lui (qu'un nouvel essai dupliquerait).
    try:
        contenu = trouve.chemin.read_bytes()
    except OSError:
        raise DonneesInvalides("Ce fichier ne peut pas être lu (disponible en ligne seulement, sur Google Drive ou OneDrive ?). "
                               "Ouvre-le une fois pour qu'il soit téléchargé, puis réessaie.") from None
    fichiers.verifier_fichier(trouve.chemin.name, contenu)
    if action == "creer":
        prop = proposition(trouve)
        source = memoire.ajouter_source(Source(
            type="article_revue", titre=prop["titre"], auteurs=prop["auteurs"], annee=prop["annee"],
            champs={"doi": prop["doi"]} if prop["doi"] else {}, statut=trouve.statut, provenance="depot_fichier"))
    elif action == "joindre":
        source = memoire._source(source_id or "")
        if source.fichier_joint:
            raise DonneesInvalides("Cette source a déjà un fichier joint : remplace-le depuis sa fiche si besoin.")
        if source.statut == "a_lire" and trouve.statut == "lu":
            memoire.modifier_source(source.id, statut="lu")  # le dossier « LUS » en sait plus ; jamais l'inverse
    else:
        raise DonneesInvalides(f"Action inconnue : « {action} ».")
    try:
        memoire.joindre_fichier(source.id, trouve.chemin.name, contenu)
    except Exception:
        if action == "creer":  # écriture impossible : retirer la source qu'on vient de créer
            memoire.supprimer_source(source.id, confirme=True)
        raise
    source.origine_import = {**(source.origine_import or {}), **origine}
    memoire.enregistrer()
    return {"source_id": source.id}
