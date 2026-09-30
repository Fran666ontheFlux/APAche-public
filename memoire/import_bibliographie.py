"""Import d'une bibliographie existante (une première partie, un travail préparatoire…).

Chaque référence APA du .docx est découpée en champs, puis proposée à
l'utilisateur, une par une : fusionner avec une source déjà là (même auteur,
année compatible), créer une nouvelle source, ou passer. Jamais de fusion en
silence. Toute référence importée est marquée `citee_partie1`.

Le découpage s'appuie sur l'italique du fichier Word : il dit où finit le
titre et où commence la revue ou l'ouvrage. Il reste une proposition : la
fiche de la source permet de tout corriger ensuite.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from . import apa
from .depot import Memoire
from .import_extraits import W, _actif, ouvrir_docx
from .modele import DonneesInvalides, Source

STYLES_TITRE = re.compile(r"^(Heading|Titre|Title)", re.IGNORECASE)
DATE = re.compile(r"\((?P<annee>\d{4}[a-z]?|s\.\s?d\.)(?:,\s*(?P<date>[^)]+))?\)\s*[.,]?\s*")
INITIALES = re.compile(r"^(?:[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]{0,2}\.[\s-]*)+$")  # « C. G. », « J.-P. », « Ch. »
LIEN = re.compile(r"(?:https?://\S+|(?:doi\s*:?\s*)10\.\d{4,9}/\S+)", re.IGNORECASE)
CHAPITRE = re.compile(r"[.?!]\s+(?:Dans|In)\s+(?P<directeurs>.+?)\s*\((?:dir|[ée]ds?|Eds?)\.\)\s*,\s*", re.IGNORECASE)
# Revue, volume(numéro), pages — le volume ou le numéro suffit : « Géorama, (1) », « GéoRevue, 26 ».
ARTICLE = re.compile(r"^(?P<revue>.+?),\s*(?:vol\.\s*)?(?P<volume>\d[\w‑–-]*)?\s*(?:\((?P<numero>[^)]+)\))?"
                     r"(?:,\s*(?:pp?\.\s*)?(?P<pages>\d+\s*[-‑–]\s*\d+))?\s*[.,]?\s*$")
SEUIL_NOM = 0.8  # « Hartman » / « Hartmann », « Wisnieski » / « Wisniewski »


@dataclass
class ReferenceLue:
    segments: list[tuple[str, bool]]
    section: str = ""  # titre de partie au-dessus : « Sources juridiques », « Sitographie »…

    @property
    def texte(self) -> str:
        return "".join(t for t, _ in self.segments).strip()

    @property
    def html(self) -> str:
        return "".join(f"<i>{escape(t, quote=False)}</i>" if i else escape(t, quote=False) for t, i in self.segments).strip()

    @property
    def empreinte(self) -> str:
        return hashlib.sha1(" ".join(self.texte.split()).casefold().encode("utf-8")).hexdigest()[:16]


@dataclass
class Proposition:
    type: str
    auteurs: list[dict]
    annee: str
    titre: str
    champs: dict
    a_verifier: list[str] = field(default_factory=list)

    def source(self) -> Source:
        return Source(type=self.type, auteurs=self.auteurs, annee=self.annee, titre=self.titre, champs=self.champs)


# --- Lecture du .docx -----------------------------------------------------------------

def lire_references(chemin: Path) -> list[ReferenceLue]:
    document, _ = ouvrir_docx(chemin)
    references, section = [], ""
    for p in document.iter(W + "p"):
        style = p.find(f"{W}pPr/{W}pStyle")
        style = style.get(W + "val") if style is not None else ""
        segments = []
        for r in p.iter(W + "r"):
            texte = "".join(n.text or "" if n.tag == W + "t" else " " for n in r if n.tag in (W + "t", W + "tab"))
            if texte:
                italique = _actif(r.find(W + "rPr"), "i") and bool(texte.strip())
                if segments and segments[-1][1] == italique:
                    segments[-1] = (segments[-1][0] + texte, italique)
                else:
                    segments.append((texte, italique))
        texte = "".join(t for t, _ in segments).strip()
        if not texte:
            continue
        if STYLES_TITRE.match(style):
            section = texte.rstrip(" :")
            continue
        references.append(ReferenceLue(segments, section))
    if not references:
        raise DonneesInvalides("Aucune référence trouvée dans ce document : une référence par paragraphe est attendue.")
    return references


# --- Découpage d'une référence ------------------------------------------------------------

def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if not unicodedata.combining(c)).casefold()


def auteurs_depuis(texte: str) -> list[dict]:
    """« Hartmann, R., & Keller, C. G. » → deux personnes ; « Lumen. » ou
    « Conseil d'État, Section du contentieux administratif. » → une organisation."""
    texte = texte.strip()
    jetons = [j.strip() for j in re.split(r"\s*,\s*|\s+(?:&|et)\s+", re.sub(r",?\s+(?:&|et)\s+", ", ", texte)) if j.strip()]
    personnes, i = [], 0
    while i < len(jetons):
        nom = jetons[i]
        if i + 1 < len(jetons) and INITIALES.match(jetons[i + 1]):
            personnes.append({"nom": nom, "prenom": jetons[i + 1]})
            i += 2
            continue
        colle = re.match(r"^(?P<nom>.+?)\s+(?P<init>(?:[A-ZÀ-Þ][a-zà-ÿ]{0,2}\.[\s-]*)+)$", nom)  # « Hood Ch. »
        if colle and len(jetons) == 1:
            personnes.append({"nom": colle["nom"], "prenom": colle["init"].strip()})
            i += 1
            continue
        return [{"organisation": texte.rstrip(".").strip()}] if texte.rstrip(".").strip() else []
    return personnes


def _directeurs(texte: str) -> list[dict]:
    """« M.-P. Boucheron & F. Lestrade » : initiales avant le nom."""
    personnes = []
    for morceau in re.split(r"\s*,\s*|\s+(?:&|et)\s+", texte.strip()):
        m = re.match(r"^(?P<init>(?:[A-ZÀ-Þ][a-zà-ÿ]{0,2}\.[\s-]*)+)\s*(?P<nom>.+)$", morceau.strip())
        if m:
            personnes.append({"nom": m["nom"].strip(), "prenom": m["init"].strip()})
        elif morceau.strip():
            personnes.append({"nom": morceau.strip(), "prenom": ""})
    return personnes


def _lien(texte: str) -> tuple[str, dict]:
    """Retire le DOI ou l'adresse de fin ; renvoie le reste et le champ trouvé."""
    liens = list(LIEN.finditer(texte))
    if not liens:
        return texte, {}
    m = liens[-1]
    lien = m.group().rstrip(".,;")
    reste = (texte[:m.start()] + texte[m.end():]).strip()
    if "doi.org" in lien.casefold() or re.match(r"(?:doi\s*:?\s*)?10\.", lien, re.IGNORECASE):
        return reste, {"doi": apa.doi_en_url(lien)}
    return reste, {"url": lien}


def _phrases(texte: str) -> list[str]:
    return [p.strip(" .") for p in re.split(r"\.\s+", texte.strip(" .")) if p.strip(" .")]


def _precision(titre: str, apres: str) -> tuple[str, str, str]:
    """« Titre [Version consolidée] » : la précision entre crochets, où qu'elle soit."""
    m = re.search(r"\s*\[(?P<p>[^\]]+)\]\s*$", titre)
    if m:
        return titre[:m.start()].strip(), m["p"].strip(), apres
    m = re.match(r"^\s*\[(?P<p>[^\]]+)\]\s*\.?\s*", apres)
    if m:
        return titre, m["p"].strip(), apres[m.end():]
    return titre, "", apres


def analyser(ref: ReferenceLue) -> Proposition:
    texte = " ".join(ref.texte.split())
    # Positions de l'italique dans le texte à espaces normalisés.
    italiques, pos = [], 0
    for morceau, italique in ref.segments:
        propre = " ".join(morceau.split())
        debut = texte.find(propre, pos) if propre else -1
        if debut >= 0:
            if italique:
                italiques.append((debut, debut + len(propre)))
            pos = debut + len(propre)

    m = DATE.search(texte)
    if not m:
        return Proposition("article_revue", [], "", texte, {}, ["Année introuvable : la référence est laissée entière dans le titre."])
    auteurs = auteurs_depuis(texte[:m.start()])
    # « 2020a » : la lettre est recalculée par l'outil parmi toutes les sources (apa.suffixes), pas stockée.
    annee = "" if m["annee"].startswith("s") else m["annee"][:4]
    date_precise = (m["date"] or "").strip()
    debut_reste = m.end()
    reste = texte[debut_reste:]
    italiques = [(a - debut_reste, b - debut_reste) for a, b in italiques if a >= debut_reste]
    notes, champs = [], {}
    if date_precise:
        champs["date_precise"] = date_precise
    section = _sans_accents(ref.section)

    # Chapitre d'ouvrage collectif : « Titre. Dans A. Dir (dir.), Ouvrage (p. x-y). Éditeur. »
    ch = CHAPITRE.search(reste)
    if ch and "jurid" not in section:
        titre = reste[:ch.start() + 1].strip(" .")
        suite, lien = _lien(reste[ch.end():])
        pages = re.search(r"\s*\((?:[^()]*?)(?:pp?\.)\s*(?P<pages>[^)]+)\)", suite)
        ouvrage = suite[:pages.start()] if pages else suite.split(". ")[0]
        editeur = _phrases(suite[pages.end():] if pages else suite[len(ouvrage):])
        champs.update(directeurs=_directeurs(ch["directeurs"]), titre_ouvrage=ouvrage.strip(" .,"), **lien)
        if pages and re.search(r"\d", pages["pages"]):
            champs["pages"] = pages["pages"].strip()
        elif pages:
            notes.append(f"Pages « {pages['pages'].strip()} » ignorées : ce ne sont pas des numéros.")
        if editeur:
            champs["editeur"] = editeur[0]
        return Proposition("chapitre", auteurs, annee, titre, champs, notes)

    # Titre : en italique en tête (œuvre autonome), sinon jusqu'au premier italique ou au premier point.
    if italiques and italiques[0][0] <= 1:
        titre, apres = reste[italiques[0][0]:italiques[0][1]], reste[italiques[0][1]:]
        titre_italique = True
    elif italiques:
        titre, apres = reste[:italiques[0][0]], reste[italiques[0][0]:]
        titre_italique = False
    else:
        coupe = re.search(r"(?<=[.?!])\s+", reste)
        titre, apres = (reste[:coupe.start()], reste[coupe.end():]) if coupe else (reste, "")
        titre_italique = False
    titre = titre.strip().rstrip(".,").strip()
    titre, precision, apres = _precision(titre, apres)
    apres, lien = _lien(apres.strip(" .,"))
    champs.update(lien)
    phrases = _phrases(apres)

    if "jurid" in section:
        type_ = "jurisprudence" if re.match(r"(Arr[êe]t|Jugement|D[ée]cision|Ordonnance de r[ée]f[ée]r[ée])", titre) else "texte_legal"
        if precision:
            champs["precision"] = precision
        if phrases and type_ == "texte_legal":
            champs["publication"] = phrases[0]
        return Proposition(type_, auteurs, annee, titre, champs, notes)
    if "sito" in section or "site" in section:
        if phrases:
            champs["site"] = phrases[0]
        notes.append("Date de consultation à ajouter (Guide du Master).")
        return Proposition("page_web", auteurs, annee, titre, champs, notes)

    colloque = re.search(r"communication pr[ée]sent[ée]e\s+(?:au|à|lors du|lors de la|lors de l')\s*(?P<ou>.+)", apres, re.IGNORECASE)
    if colloque:
        evenement, _, lieu = colloque["ou"].strip(" .").rpartition(", ")
        champs["evenement"] = apa._majuscule(evenement or lieu)
        if evenement and lieu:
            champs["lieu"] = lieu
        return Proposition("communication_colloque", auteurs, annee, titre, champs, notes)

    cours = re.search(r"\b(syllabus|notes de cours)\b", apres, re.IGNORECASE)
    if cours:
        champs["nature"] = apa._majuscule(cours.group(1).casefold())
        institution = next((p for p in phrases if re.search(r"universit|[ée]cole|institut", p, re.IGNORECASE)), "")
        if institution:
            champs["institution"] = institution
        return Proposition("support_cours", auteurs, annee, titre, champs, notes)

    if precision and re.match(r"(th[èe]se|m[ée]moire)", precision, re.IGNORECASE):
        champs["nature"] = precision
        if phrases:
            champs["institution"] = phrases[0]
        return Proposition("memoire_these", auteurs, annee, titre, champs, notes)

    article = ARTICLE.match(apres.strip())
    if article and (article["volume"] or article["numero"]):
        champs["revue"] = article["revue"].strip(" .,")
        for cle in ("volume", "numero", "pages"):
            if article[cle]:
                champs[cle] = article[cle].strip()
        if titre_italique:
            notes.append("Dans ton fichier, le titre de l'article est en italique : en APA, c'est la revue qui l'est.")
        return Proposition("article_revue", auteurs, annee, titre, champs, notes)

    if titre_italique and ("url" in champs or "doi" in champs) and len(phrases) <= 1:
        if phrases:
            champs["site"] = phrases[0]
        notes.append("Type deviné (page web) : vérifie-le.")
        return Proposition("page_web", auteurs, annee, titre, champs, notes)
    if titre_italique:
        if phrases:
            champs["editeur"] = phrases[-1]
        notes.append("Type deviné (livre) : vérifie-le.")
        return Proposition("livre", auteurs, annee, titre, champs, notes)
    if phrases:
        champs["revue"] = phrases[0]
    notes.append("Type deviné (article de revue) : vérifie-le.")
    return Proposition("article_revue", auteurs, annee, titre, champs, notes)


# --- Rapprochement avec les sources existantes ----------------------------------------------

def _noms(auteurs: list[dict]) -> list[str]:
    noms = []
    for a in auteurs:
        nom = _sans_accents(a.get("nom") or a.get("organisation") or "")
        noms.extend(w for w in re.findall(r"[^\W\d_]{3,}", nom))
    return noms


def _mots_source(s: Source) -> set[str]:
    mots = set(_noms(s.auteurs))
    onglet = (s.origine_import or {}).get("onglet", "")
    mots.update(re.findall(r"[^\W\d_]{3,}", _sans_accents(onglet)))
    return mots


def candidats(memoire: Memoire, prop: Proposition, empreinte: str) -> list[dict]:
    noms = _noms(prop.auteurs)
    trouves = []
    for s in memoire.sources.values():
        if (s.origine_import or {}).get("reference_biblio") not in (None, empreinte):
            continue  # déjà rapprochée d'une autre référence de la bibliographie
        if s.annee and prop.annee and s.annee[:4] != prop.annee[:4]:
            continue
        mots = _mots_source(s)
        score = max((difflib.SequenceMatcher(None, n, m).ratio() for n in noms for m in mots), default=0)
        if score >= SEUIL_NOM:
            trouves.append((score, s))
    trouves.sort(key=lambda x: -x[0])
    lettres = apa.suffixes(list(memoire.sources.values()))
    hom = apa.homonymes(list(memoire.sources.values()))
    r = memoire.projet.reglages_apa
    return [{"id": s.id, "etiquette": apa.etiquette(s, r, lettres.get(s.id, ""), s.id in hom),
             "onglet": (s.origine_import or {}).get("onglet", ""), "titre": s.titre,
             "nb_extraits": len(memoire.extraits_de(s.id)), "score": round(score, 2)}
            for score, s in trouves]


# --- Aperçu et application -------------------------------------------------------------------

def _deja(memoire: Memoire, empreinte: str) -> Source | None:
    return next((s for s in memoire.sources.values()
                 if (s.origine_import or {}).get("reference_biblio") == empreinte), None)


def apercu(memoire: Memoire, chemin: Path) -> dict:
    r = memoire.projet.reglages_apa
    references = []
    for ref in lire_references(chemin):
        prop = analyser(ref)
        deja = _deja(memoire, ref.empreinte)
        mise = apa.reference(prop.source(), r)
        references.append({
            "empreinte": ref.empreinte, "original": ref.html, "section": ref.section,
            "proposition": {"type": prop.type, "libelle_type": apa.LIBELLES_TYPES[prop.type], "auteurs": prop.auteurs,
                            "annee": prop.annee, "titre": prop.titre, "champs": prop.champs},
            "reference": {"html": mise.html, "texte": mise.texte} if mise else None,
            "a_completer": mise.manques if mise else [],
            "a_verifier": prop.a_verifier,
            "candidats": [] if deja else candidats(memoire, prop, ref.empreinte),
            "deja": {"id": deja.id} if deja else None,
        })
    return {"document": Path(chemin).name, "references": references}


def appliquer(memoire: Memoire, chemin: Path, empreinte: str, action: str, source_id: str | None = None) -> dict:
    """Crée la source, ou verse la référence dans une source existante (ses extraits restent)."""
    ref = next((x for x in lire_references(chemin) if x.empreinte == empreinte), None)
    if ref is None:
        raise DonneesInvalides("Cette référence n'est plus dans le fichier : relance l'analyse.")
    if _deja(memoire, empreinte):
        raise DonneesInvalides("Cette référence a déjà été importée.")
    prop = analyser(ref)
    if action == "creer":
        source = Source(type=prop.type, auteurs=prop.auteurs, annee=prop.annee, titre=prop.titre, champs=prop.champs,
                        statut="lu", citee_partie1=True, provenance="import_bibliographie",
                        origine_import={"document": Path(chemin).name, "reference_biblio": empreinte})
        memoire.ajouter_source(source)
    elif action == "fusionner":
        source = memoire._source(source_id or "")
        origine = {**(source.origine_import or {}), "reference_biblio": empreinte}
        memoire.modifier_source(source.id, type=prop.type, auteurs=prop.auteurs, annee=prop.annee, titre=prop.titre,
                                champs={**source.champs, **prop.champs}, citee_partie1=True,
                                statut=source.statut if source.statut != "a_lire" else "lu")
        source.origine_import = origine
        memoire.enregistrer()
    else:
        raise DonneesInvalides(f"Action inconnue : « {action} ».")
    return {"source_id": source.id}
