"""Export des sources en RIS ou BibTeX (une porte de sortie).

RIS se lit dans Zotero, Mendeley, EndNote ou Word ; BibTeX dans LaTeX, Zotero
ou JabRef. On exporte soit les sources réellement citées (celles de la
bibliographie finale), soit toutes. Le fichier est produit sur le PC et
enregistré par le navigateur : rien ne part ailleurs.
"""

from __future__ import annotations

import re
import unicodedata

from .depot import Memoire
from .modele import Source

TYPES_RIS = {
    "article_revue": "JOUR", "livre": "BOOK", "chapitre": "CHAP", "article_presse": "NEWS", "rapport": "RPRT",
    "texte_legal": "STAT", "jurisprudence": "CASE", "page_web": "ELEC", "memoire_these": "THES",
    "document_institutionnel": "GEN", "audiovisuel": "VIDEO", "communication_colloque": "CPAPER",
    "support_cours": "GEN", "communication_personnelle": "PCOMM",
}
TYPES_BIBTEX = {
    "article_revue": "article", "livre": "book", "chapitre": "incollection", "article_presse": "article",
    "rapport": "techreport", "memoire_these": "phdthesis", "communication_colloque": "inproceedings",
}


def _doi(source: Source) -> str:
    m = re.search(r"10\.\d{4,9}/\S+", source.champs.get("doi", ""))
    return m.group() if m else ""


def _pages(source: Source) -> tuple[str, str]:
    pages = re.split(r"\s*[-‐‑–—]\s*", str(source.champs.get("pages", "")).strip(), maxsplit=1)
    return (pages[0], pages[1] if len(pages) > 1 else "")


def _personne_ris(p: dict) -> str:
    return p.get("organisation") or ", ".join(x for x in (p.get("nom", ""), p.get("prenom", "")) if x)


def _conteneur(source: Source) -> str:
    c = source.champs
    return c.get("revue") or c.get("titre_ouvrage") or c.get("journal") or c.get("site") or c.get("evenement") or ""


def ris(sources: list[Source]) -> str:
    lignes = []
    for s in sources:
        c = s.champs
        debut, fin = _pages(s)
        champs = [("TY", TYPES_RIS.get(s.type, "GEN"))]
        champs += [("AU", _personne_ris(a)) for a in s.auteurs]
        champs += [("ED", _personne_ris(d)) for d in c.get("directeurs", []) if isinstance(d, dict)]
        champs += [("TI", s.titre), ("T2", _conteneur(s)), ("PY", s.annee), ("VL", c.get("volume", "")),
                   ("IS", c.get("numero", "")), ("SP", debut), ("EP", fin),
                   ("PB", c.get("editeur") or c.get("institution") or c.get("publication") or c.get("plateforme", "")),
                   ("ET", c.get("edition", "")), ("SN", c.get("isbn", "")), ("DO", _doi(s)), ("UR", c.get("url", "")),
                   ("M3", c.get("nature", "") or c.get("precision", ""))]
        lignes += [f"{cle}  - {valeur}" for cle, valeur in champs if str(valeur).strip()]
        lignes += ["ER  - ", ""]
    return "\r\n".join(lignes)  # RIS : fins de ligne Windows, attendues par plusieurs logiciels


def _bib(valeur: str) -> str:
    return re.sub(r"([&%#_$])", r"\\\1", str(valeur).strip())


def _cle(s: Source, prises: set[str]) -> str:
    premier = s.auteurs[0] if s.auteurs else {}
    nom = premier.get("nom") or premier.get("organisation") or (s.titre.split()[0] if s.titre.split() else "source")
    ascii_ = "".join(c for c in unicodedata.normalize("NFD", nom) if c.isalnum() and ord(c) < 128).lower() or "source"
    base = f"{ascii_}{s.annee.strip()[:4] or 'sd'}"
    cle, n = base, 0
    while cle in prises:
        n += 1
        cle = base + "abcdefghijklmnopqrstuvwxyz"[(n - 1) % 26]
    prises.add(cle)
    return cle


def bibtex(sources: list[Source]) -> str:
    blocs, prises = [], set()
    for s in sources:
        c = s.champs
        debut, fin = _pages(s)
        personnes = lambda liste: " and ".join(  # noqa: E731
            "{" + p["organisation"] + "}" if p.get("organisation") else ", ".join(x for x in (p.get("nom", ""), p.get("prenom", "")) if x)
            for p in liste if isinstance(p, dict))
        type_ = TYPES_BIBTEX.get(s.type, "misc")
        champs = [("author", personnes(s.auteurs)), ("editor", personnes(c.get("directeurs", []))),
                  ("title", "{" + _bib(s.titre) + "}" if s.titre else ""),
                  ("journal" if type_ == "article" else "booktitle", _bib(_conteneur(s)) if _conteneur(s) and type_ != "book" else ""),
                  ("year", s.annee), ("volume", c.get("volume", "")), ("number", c.get("numero", "")),
                  ("pages", f"{debut}--{fin}" if fin else debut), ("publisher", _bib(c.get("editeur", ""))),
                  ("school" if type_ == "phdthesis" else "institution", _bib(c.get("institution", ""))),
                  ("edition", c.get("edition", "")), ("isbn", c.get("isbn", "")), ("doi", _doi(s)),
                  ("url", c.get("url", "")), ("note", _bib(c.get("nature", "") or c.get("precision", "")))]
        corps = ",\n".join(f"  {cle} = {{{valeur}}}" for cle, valeur in champs if str(valeur).strip())
        blocs.append(f"@{type_}{{{_cle(s, prises)},\n{corps}\n}}")
    return "\n\n".join(blocs) + "\n"


def sources_a_exporter(memoire: Memoire, lesquelles: str) -> list[Source]:
    if lesquelles == "toutes":
        choisies = list(memoire.sources.values())
    else:  # comme la bibliographie finale : un extrait intégré, ou citée en partie 1
        integrees = {e.source_id for e in memoire.extraits.values() if e.integre}
        choisies = [s for s in memoire.sources.values()
                    if s.type != "communication_personnelle" and (s.citee_partie1 or s.id in integrees)]
    return sorted(choisies, key=lambda s: (_personne_ris(s.auteurs[0]).casefold() if s.auteurs else s.titre.casefold(), s.annee))
