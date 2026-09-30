"""Compléter une source depuis son DOI (CrossRef) ou son ISBN (Open Library, BnF)

Le seul endroit de l'outil qui parle à internet, et seulement quand l'utilisateur
le demande, clic par clic, après l'avoir autorisé dans le projet (désactivé par
défaut). Ne part que l'identifiant cherché : ni nom, ni adresse e-mail, ni extrait.
Les tests de confidentialité vérifient que ce module est le seul à pouvoir
sortir, et seulement vers ces catalogues.

Le résultat est une proposition : l'utilisateur la regarde, puis remplace ou
complète sa référence. En cas d'échec (pas de réseau, identifiant inconnu), un
message clair ; la saisie à la main reste possible.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .modele import DonneesInvalides

CROSSREF = "https://api.crossref.org/works/"
OPEN_LIBRARY = "https://openlibrary.org"
# Catalogue de la Bibliothèque nationale de France : les livres en français qu'Open Library ignore souvent.
BNF = "https://catalogue.bnf.fr/api/SRU"
ADRESSES = (CROSSREF, OPEN_LIBRARY, BNF)
DC = "{http://purl.org/dc/elements/1.1/}"
DELAI = 10  # secondes
# Un nom neutre : CrossRef invite à donner une adresse e-mail, on ne la donne pas.
AGENT = "apache-outil-local/1.0"

TYPES_CROSSREF = {
    "journal-article": "article_revue", "book": "livre", "monograph": "livre", "edited-book": "livre",
    "reference-book": "livre", "book-chapter": "chapitre", "book-section": "chapitre", "book-part": "chapitre",
    "reference-entry": "chapitre", "proceedings-article": "chapitre", "report": "rapport",
    "dissertation": "memoire_these", "posted-content": "page_web",
}


class Inconnu(DonneesInvalides):
    """Le service ne connaît pas cet identifiant : un autre catalogue le connaît peut-être."""


def _obtenir(url: str, xml: bool = False):
    """La réponse du service : un dict (JSON), ou un élément XML (catalogue de la BnF)."""
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT,
                                                   "Accept": "application/xml" if xml else "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
            return ET.fromstring(reponse.read()) if xml else json.load(reponse)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise Inconnu("Identifiant inconnu du service : vérifie-le, ou remplis la référence à la main.") from None
        raise DonneesInvalides(f"Le service en ligne a répondu par une erreur ({e.code}). Réessaie plus tard, "
                               f"ou remplis la référence à la main.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise DonneesInvalides("Pas de réponse : pas de connexion à internet, ou le service est indisponible. "
                               "Remplis la référence à la main : rien n'est perdu.") from None
    except (json.JSONDecodeError, ET.ParseError):
        raise DonneesInvalides("Réponse illisible du service en ligne. Remplis la référence à la main.") from None


# --- Identifiants -----------------------------------------------------------------

def normaliser_doi(texte: str) -> str:
    m = re.search(r"10\.\d{4,9}/\S+", str(texte).strip())
    if not m:
        raise DonneesInvalides("Ce n'est pas un DOI : il commence par « 10. » (ex. 10.1177/0042098016630507).")
    return m.group().rstrip(".,;)")


def normaliser_isbn(texte: str) -> str:
    isbn = re.sub(r"[\s-]", "", str(texte)).upper()
    if re.fullmatch(r"\d{9}[\dX]", isbn):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(isbn))
        valide = total % 11 == 0
    elif re.fullmatch(r"\d{13}", isbn):
        valide = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn)) % 10 == 0
    else:
        valide = False
    if not valide:
        raise DonneesInvalides("Ce n'est pas un ISBN valide (10 ou 13 chiffres) : vérifie-le au dos du livre.")
    return isbn


def identifier(texte: str) -> tuple[str, str]:
    """(« doi » | « isbn », identifiant normalisé), selon ce que l'utilisateur a tapé."""
    return ("doi", normaliser_doi(texte)) if "10." in str(texte) else ("isbn", normaliser_isbn(texte))


# --- Réponses → champs de l'outil -------------------------------------------------------

def _texte(valeur) -> str:
    if isinstance(valeur, list):
        valeur = valeur[0] if valeur else ""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", str(valeur or ""))).split())


def _personnes(liste) -> list[dict]:
    personnes = []
    for p in liste or []:
        if p.get("family"):
            personnes.append({"nom": _texte(p["family"]), "prenom": _texte(p.get("given", ""))})
        elif p.get("name"):
            personnes.append({"organisation": _texte(p["name"])})
    return personnes


def depuis_crossref(message: dict) -> dict:
    type_ = TYPES_CROSSREF.get(message.get("type", ""), "article_revue")
    titre = _texte(message.get("title"))
    sous_titre = _texte(message.get("subtitle"))
    if sous_titre and sous_titre.casefold() not in titre.casefold():
        titre = f"{titre} : {sous_titre}"
    # L'année du numéro imprimé d'abord : c'est celle d'une référence APA (article en ligne en 2016, dans le numéro de 2017).
    date = next((message[c]["date-parts"][0] for c in ("published-print", "issued", "published-online", "published")
                 if message.get(c, {}).get("date-parts", [[None]])[0][0]), [None])
    conteneur = _texte(message.get("container-title"))
    champs = {"doi": f"https://doi.org/{message['DOI']}"} if message.get("DOI") else {}
    if type_ == "article_revue":
        champs.update(revue=conteneur, volume=_texte(message.get("volume")), numero=_texte(message.get("issue")),
                      pages=_texte(message.get("page")))
    elif type_ == "chapitre":
        champs.update(titre_ouvrage=conteneur, pages=_texte(message.get("page")), editeur=_texte(message.get("publisher")),
                      directeurs=_personnes(message.get("editor")))
    elif type_ in ("livre", "rapport"):
        champs.update(editeur=_texte(message.get("publisher")))
        if message.get("type") == "edited-book":
            champs["dirige"] = True
    if message.get("ISBN") and type_ in ("livre", "chapitre"):
        champs["isbn"] = _texte(message["ISBN"])
    auteurs = _personnes(message.get("author")) or (_personnes(message.get("editor")) if message.get("type") == "edited-book" else [])
    return {"type": type_, "auteurs": auteurs, "annee": str(date[0]) if date[0] else "", "titre": titre,
            "champs": {k: v for k, v in champs.items() if v}}


def _personne_nom_complet(nom: str) -> dict:
    """« Mira Holt » → nom Holt, prénom Mira (Open Library donne le nom en entier)."""
    mots = _texte(nom).split()
    return {"nom": mots[-1], "prenom": " ".join(mots[:-1])} if mots else {}


def depuis_open_library(isbn: str, livre: dict, noms_auteurs: list[str]) -> dict:
    """Une édition d'Open Library (/isbn/…json) ; ses auteurs n'y sont que des renvois, d'où `noms_auteurs`."""
    titre = _texte(livre.get("title"))
    if livre.get("subtitle"):
        titre = f"{titre} : {_texte(livre['subtitle'])}"
    auteurs = [p for p in map(_personne_nom_complet, noms_auteurs) if p]
    if not auteurs and livre.get("by_statement"):  # « Mira Holt » écrit sur la page de titre
        auteurs = [p for p in map(_personne_nom_complet, re.split(r",| and | et ", _texte(livre["by_statement"]))) if p]
    annee = re.search(r"(?:1[5-9]|20)\d{2}", _texte(livre.get("publish_date")))
    editeurs = livre.get("publishers") or [""]
    editeur = editeurs[0].get("name", "") if isinstance(editeurs[0], dict) else editeurs[0]
    champs = {"isbn": isbn, "editeur": _texte(editeur)}
    return {"type": "livre", "auteurs": auteurs, "annee": annee.group() if annee else "", "titre": titre,
            "champs": {k: v for k, v in champs.items() if v}}


def _open_library(isbn: str) -> dict:
    livre = _obtenir(f"{OPEN_LIBRARY}/isbn/{isbn}.json")  # renvoie vers /books/…json ; 404 si inconnu
    noms = []
    for a in (livre.get("authors") or [])[:10]:
        cle = a.get("key", "") if isinstance(a, dict) else ""
        if re.fullmatch(r"/authors/OL\d+A", cle):
            noms.append(_obtenir(f"{OPEN_LIBRARY}{cle}.json").get("name", ""))
    return depuis_open_library(isbn, livre, noms)


ROLES_AUTEUR = ("auteur", "author")
ROLES_DIRECTEUR = ("directeur de publication", "éditeur scientifique", "editor")


def _personne_bnf(texte: str) -> tuple[dict, str]:
    """« Slater, Tom (1975-....). Auteur du texte » → ({nom, prenom}, « auteur du texte »)."""
    nom, _, role = texte.partition(". ")
    nom = re.sub(r"\s*\([^)]*\)", "", nom).strip(" .")
    famille, _, prenom = nom.partition(",")
    return ({"nom": famille.strip(), "prenom": prenom.strip()} if prenom else {"organisation": famille.strip()}), role.casefold()


def depuis_bnf(isbn: str, notice: ET.Element) -> dict:
    """Une notice Dublin Core du catalogue de la BnF."""
    valeurs = lambda cle: [_texte(e.text) for e in notice.iter(DC + cle) if e.text and e.text.strip()]  # noqa: E731
    titre = (valeurs("title") or [""])[0].split(" / ")[0].strip()
    auteurs, directeurs = [], []
    for texte in valeurs("creator") + valeurs("contributor"):
        personne, role = _personne_bnf(texte)
        if any(r in role for r in ROLES_DIRECTEUR):
            directeurs.append(personne)
        elif not role or any(r in role for r in ROLES_AUTEUR):
            auteurs.append(personne)
    annee = re.search(r"(?:1[5-9]|20)\d{2}", " ".join(valeurs("date")))
    editeur = re.sub(r"\s*\([^)]*\)", "", (valeurs("publisher") or [""])[0]).strip()
    champs = {"isbn": isbn, "editeur": editeur}
    if directeurs and not auteurs:
        auteurs, champs["dirige"] = directeurs, True
    return {"type": "livre", "auteurs": auteurs, "annee": annee.group() if annee else "", "titre": titre,
            "champs": {k: v for k, v in champs.items() if v}}


def _bnf(isbn: str) -> dict:
    requete = urllib.parse.quote(f'bib.isbn all "{isbn}"')
    reponse = _obtenir(f"{BNF}?version=1.2&operation=searchRetrieve&query={requete}"
                       f"&recordSchema=dublincore&maximumRecords=1", xml=True)
    notice = next((e for e in reponse.iter() if e.tag.endswith("}dc")), None)
    if notice is None:
        raise Inconnu("La BnF ne connaît pas cet ISBN.")
    return depuis_bnf(isbn, notice)


def _francophone(isbn: str) -> bool:
    """ISBN attribué en zone francophone (France, Belgique, Suisse, Québec…) : 978-2, 979-10, ou ISBN-10 en 2."""
    return isbn.startswith(("9782", "97910")) or (len(isbn) == 10 and isbn.startswith("2"))


def chercher(texte: str) -> dict:
    """Interroge CrossRef (DOI), ou Open Library et la BnF (ISBN). N'est appelé que sur demande explicite
    de l'utilisateur. Pour un ISBN, le catalogue qui a le plus de chances de connaître le livre d'abord."""
    genre, identifiant = identifier(texte)
    if genre == "doi":
        reponse = _obtenir(CROSSREF + urllib.parse.quote(identifiant, safe="/"))
        return {"service": "CrossRef", "identifiant": identifiant, **depuis_crossref(reponse.get("message") or {})}
    catalogues = [("BnF", _bnf), ("Open Library", _open_library)]
    if not _francophone(identifiant):
        catalogues.reverse()
    for service, interroger in catalogues:
        try:
            return {"service": service, "identifiant": identifiant, **interroger(identifiant)}
        except Inconnu:
            continue
    raise DonneesInvalides("Ni Open Library ni la BnF ne connaissent cet ISBN : vérifie-le, "
                           "ou remplis la référence à la main.")
