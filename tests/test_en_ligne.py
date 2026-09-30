"""DOI et ISBN : les réponses des services sont simulées. Aucun test n'appelle internet."""

import xml.etree.ElementTree as ET

from outils import lancer

from memoire import apa, en_ligne
from memoire.modele import DonneesInvalides, ReglagesAPA, Source
from test_sources_serveur import avec_client

# Réponses réduites à ce que l'outil lit, dans la forme renvoyée par CrossRef et Open Library.
ARTICLE_CROSSREF = {"message": {
    "type": "journal-article", "DOI": "10.9999/0042098016630507",
    "title": ["Rooftop beekeeping transformations beyond the hobby/industry dichotomy"],
    "author": [{"given": "Xavi", "family": "Arrieta", "sequence": "first"}],
    "container-title": ["Green Studies"], "volume": "54", "issue": "4", "page": "953-970",
    "issued": {"date-parts": [[2016, 2, 29]]}, "published-print": {"date-parts": [[2017, 3]]},
    "publisher": "SAGE Publications",
}}
CHAPITRE_CROSSREF = {"message": {
    "type": "book-chapter", "DOI": "10.1007/978-1-4020-6709-9_117",
    "title": ["Expression of the <i>manganese</i> stabilising protein"], "container-title": ["Photosynthesis. Energy from the Sun"],
    "author": [{"given": "Alice", "family": "Williamson"}], "editor": [{"given": "John F.", "family": "Allen"}],
    "page": "525-528", "publisher": "Springer Netherlands", "ISBN": ["9781402067075"], "issued": {"date-parts": [[2008]]},
}}
# Une édition d'Open Library (/isbn/…json) : les auteurs n'y sont que des renvois vers /authors/…json.
LIVRE_OPEN_LIBRARY = {
    "title": "The greening of rooftops and the price of shade",
    "subtitle": "planting policies in Chicago",
    "authors": [{"key": "/authors/OL7042744A"}], "publishers": ["Routledge"], "publish_date": "Jul 03, 2012",
}
AUTEUR_OPEN_LIBRARY = {"name": "Mira Holt"}
# Réponse du catalogue de la BnF (SRU, Dublin Core), réduite.
NOTICE_BNF = ET.fromstring("""<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
<srw:numberOfRecords>1</srw:numberOfRecords><srw:records><srw:record><srw:recordData>
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Vous avez dit chimie ? : de la cuisine au salon, des molécules plein la maison / Yves Verchier, Nathalie Gerber</dc:title>
<dc:creator>Verchier, Yves (1956-....). Auteur du texte</dc:creator>
<dc:creator>Gerber, Nathalie. Auteur du texte</dc:creator>
<dc:contributor>Dupont, Jean. Illustrateur</dc:contributor>
<dc:publisher>Dunod (Paris)</dc:publisher><dc:date>2011</dc:date>
</oai_dc:dc></srw:recordData></srw:record></srw:records></srw:searchRetrieveResponse>""")
BNF_VIDE = ET.fromstring('<r xmlns:srw="http://www.loc.gov/zing/srw/"><srw:numberOfRecords>0</srw:numberOfRecords></r>')


class FauxService:
    """Remplace l'appel réseau : enregistre l'adresse demandée, renvoie la réponse prévue.
    `reponse` : la même pour tout appel, ou {début d'adresse: réponse} (une exception y est levée)."""

    def __init__(self, reponse=None, erreur=None):
        self.reponse, self.erreur, self.adresses = reponse, erreur, []

    def __enter__(self):
        self.origine = en_ligne._obtenir

        def faux(url, xml=False):
            self.adresses.append(url)
            if self.erreur:
                raise self.erreur
            if isinstance(self.reponse, dict) and self.reponse and all(k.startswith("http") for k in self.reponse):
                reponse = next(v for k, v in self.reponse.items() if url.startswith(k))
                if isinstance(reponse, Exception):
                    raise reponse
                return reponse
            return self.reponse

        en_ligne._obtenir = faux
        return self

    def __exit__(self, *_):
        en_ligne._obtenir = self.origine


def test_identifiants():
    assert en_ligne.identifier("https://doi.org/10.9999/0042098016630507.") == ("doi", "10.9999/0042098016630507")
    assert en_ligne.identifier("DOI : 10.9999/esp.171.0073") == ("doi", "10.9999/esp.171.0073")
    assert en_ligne.identifier("978-2-10-054537-7") == ("isbn", "9782100545377")
    assert en_ligne.identifier("2-10-054537-x") == ("isbn", "210054537X")  # ISBN-10 dont la clé est X
    for faux in ("978-2-10-054537-8", "12345", "pas un identifiant"):
        try:
            en_ligne.identifier(faux)
            raise AssertionError(faux)
        except DonneesInvalides:
            pass


def test_article_depuis_crossref():
    with FauxService(ARTICLE_CROSSREF) as service:
        p = en_ligne.chercher("10.9999/0042098016630507")
    assert service.adresses == ["https://api.crossref.org/works/10.9999/0042098016630507"]  # seul le DOI part
    # Publié en ligne en 2016, dans le numéro imprimé de 2017 : la référence APA porte 2017.
    assert p["service"] == "CrossRef" and p["type"] == "article_revue" and p["annee"] == "2017"
    source = Source(type=p["type"], auteurs=p["auteurs"], annee=p["annee"], titre=p["titre"], champs=p["champs"])
    assert apa.reference(source, ReglagesAPA()).texte == (
        "Arrieta, X. (2017). Rooftop beekeeping transformations beyond the hobby/industry "
        "dichotomy. Green Studies, 54(4), 953-970. https://doi.org/10.9999/0042098016630507")


def test_chapitre_depuis_crossref():
    with FauxService(CHAPITRE_CROSSREF):
        p = en_ligne.chercher("10.1007/978-1-4020-6709-9_117")
    assert p["type"] == "chapitre" and p["titre"] == "Expression of the manganese stabilising protein"  # balises ôtées
    assert p["champs"]["directeurs"] == [{"nom": "Allen", "prenom": "John F."}]
    assert (p["champs"]["titre_ouvrage"], p["champs"]["pages"], p["champs"]["isbn"]) == (
        "Photosynthesis. Energy from the Sun", "525-528", "9781402067075")


INCONNU = en_ligne.Inconnu("inconnu")


def test_livre_anglais_depuis_open_library():
    with FauxService({"https://openlibrary.org/isbn/": LIVRE_OPEN_LIBRARY,
                      "https://openlibrary.org/authors/": AUTEUR_OPEN_LIBRARY}) as service:
        p = en_ligne.chercher("978-0-00-000000-2")
    # Open Library d'abord pour un ISBN hors zone francophone ; la BnF n'est pas dérangée.
    assert service.adresses == ["https://openlibrary.org/isbn/9780000000002.json",
                                "https://openlibrary.org/authors/OL7042744A.json"]
    assert p["service"] == "Open Library" and p["auteurs"] == [{"nom": "Holt", "prenom": "Mira"}]
    assert (p["titre"], p["annee"], p["champs"]) == (
        "The greening of rooftops and the price of shade : planting policies in Chicago",
        "2012", {"isbn": "9780000000002", "editeur": "Routledge"})


def test_livre_francais_depuis_la_bnf():
    with FauxService({"https://catalogue.bnf.fr/": NOTICE_BNF}) as service:
        p = en_ligne.chercher("978-2-10-054537-7")
    assert len(service.adresses) == 1 and service.adresses[0].startswith("https://catalogue.bnf.fr/api/SRU?")
    assert "9782100545377" in service.adresses[0]
    assert p["service"] == "BnF"
    assert p["auteurs"] == [{"nom": "Verchier", "prenom": "Yves"}, {"nom": "Gerber", "prenom": "Nathalie"}]  # pas l'illustrateur
    assert (p["titre"], p["annee"], p["champs"]) == (
        "Vous avez dit chimie ? : de la cuisine au salon, des molécules plein la maison", "2011",
        {"isbn": "9782100545377", "editeur": "Dunod"})


def test_un_catalogue_prend_le_relais_de_l_autre():
    with FauxService({"https://catalogue.bnf.fr/": NOTICE_BNF, "https://openlibrary.org/": INCONNU}) as service:
        p = en_ligne.chercher("9780000000002")
    assert p["service"] == "BnF"
    assert [a[:24] for a in service.adresses] == ["https://openlibrary.org/", "https://catalogue.bnf.fr"]
    with FauxService({"https://catalogue.bnf.fr/": BNF_VIDE, "https://openlibrary.org/isbn/": LIVRE_OPEN_LIBRARY,
                      "https://openlibrary.org/authors/": AUTEUR_OPEN_LIBRARY}):
        assert en_ligne.chercher("9782100545377")["service"] == "Open Library"


def test_echecs_expliques():
    with FauxService({"https://catalogue.bnf.fr/": BNF_VIDE, "https://openlibrary.org/": INCONNU}):
        try:
            en_ligne.chercher("9782100545377")
            raise AssertionError("ISBN inconnu accepté")
        except DonneesInvalides as e:
            assert "ne connaissent cet ISBN" in str(e)
    with FauxService(erreur=DonneesInvalides("Pas de réponse : pas de connexion à internet")):
        try:
            en_ligne.chercher("10.9999/0042098016630507")
            raise AssertionError("aurait dû échouer")
        except DonneesInvalides as e:
            assert "à internet" in str(e)


@avec_client
def test_par_le_serveur_apres_autorisation(client):
    statut, _ = client("PATCH", "/api/projet", {"recherche_en_ligne": "oui"})
    assert statut == 400  # oui ou non, pas du texte
    client("PATCH", "/api/projet", {"recherche_en_ligne": True})
    with FauxService(ARTICLE_CROSSREF):
        statut, r = client("POST", "/api/en-ligne", {"identifiant": "10.9999/0042098016630507"})
    assert statut == 200 and r["proposition"]["auteurs"][0]["nom"] == "Arrieta"
    assert "<i>Green Studies, 54</i>" in r["reference"]["html"]
    client("PATCH", "/api/projet", {"recherche_en_ligne": False})
    statut, _ = client("POST", "/api/en-ligne", {"identifiant": "10.9999/0042098016630507"})
    assert statut == 403  # désactivée à nouveau : refusé


if __name__ == "__main__":
    lancer(globals())
