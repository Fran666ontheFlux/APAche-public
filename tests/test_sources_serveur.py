import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from outils import dossier_temporaire, lancer

from memoire.application import Application
from memoire.serveur import creer_serveur

# Le vrai serveur, sur un port libre, avec un dossier de données jetable :
# on teste les routes telles que l'interface les appelle.


class Client:
    def __init__(self, dossier):
        self.app = Application(fichier_reglages=Path(dossier) / "reglages.json")
        self.app.ouvrir(str(Path(dossier) / "donnees"), creer=True)
        self.serveur = creer_serveur(self.app, 0)
        self.port = self.serveur.server_address[1]
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def __call__(self, methode, chemin, corps=None):
        requete = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{chemin}", method=methode,
            data=None if corps is None else json.dumps(corps).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(requete) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def fermer(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        self.app.fermer()


def avec_client(test):
    def lance():
        with dossier_temporaire() as d:
            client = Client(d)
            try:
                test(client)
            finally:
                client.fermer()
    lance.__name__ = test.__name__
    return lance


@avec_client
def test_schema_couvre_tous_les_types(client):
    statut, schema = client("GET", "/api/schema")
    assert statut == 200
    types = {t["cle"]: t for t in schema["types"]}
    assert types["chapitre"]["libelle"] == "Chapitre d'ouvrage collectif"
    assert {"cle": "pages", "libelle": "Pages du chapitre (ex. 29-43)", "obligatoire": True, "genre": "texte"} \
        in types["chapitre"]["champs"]
    assert [n["cle"] for n in schema["natures"]] == ["citation", "paraphrase", "idee_perso"]


@avec_client
def test_creer_modifier_et_lister_une_source(client):
    statut, vue = client("POST", "/api/sources", {"type": "article_revue"})
    assert statut == 200
    id_ = vue["cree"]
    assert vue["etiquette"] == "Source sans auteur ni titre"
    assert "Dans quelle revue ?" in vue["a_completer"]

    statut, vue = client("PATCH", f"/api/sources/{id_}", {
        "auteurs": [{"nom": "Arrieta", "prenom": "Xavi"}], "annee": "2017",
        "titre": "Rooftop beekeeping transformations",
        "champs": {"revue": "Green Studies", "volume": "54", "numero": "4", "pages": "953-970",
                   "doi": "10.9999/0042098016630507"}})
    assert statut == 200
    assert vue["etiquette"] == "Arrieta (2017)"
    assert vue["reference"]["html"] == ("Arrieta, X. (2017). Rooftop beekeeping transformations. "
                                        "<i>Green Studies, 54</i>(4), 953-970. https://doi.org/10.9999/0042098016630507")
    assert vue["a_completer"] == []

    statut, liste = client("GET", "/api/sources")
    assert [s["etiquette"] for s in liste["sources"]] == ["Arrieta (2017)"]
    assert liste["sources"][0]["libelle_type"] == "Article de revue"


@avec_client
def test_apercu_ne_touche_a_rien(client):
    _, vue = client("POST", "/api/sources", {"type": "livre", "titre": "Titre enregistré"})
    statut, apercu = client("POST", "/api/sources/apercu", {
        "id": vue["cree"], "type": "livre", "titre": "Titre en cours de saisie",
        "auteurs": [{"organisation": "UNESCO"}], "annee": "2022", "champs": {"editeur": "UNESCO"}})
    assert statut == 200
    assert apercu["reference"]["texte"] == "UNESCO. (2022). Titre en cours de saisie."
    _, relue = client("GET", f"/api/sources/{vue['cree']}")
    assert relue["source"]["titre"] == "Titre enregistré"


@avec_client
def test_extraits_et_leurs_citations(client):
    _, vue = client("POST", "/api/sources", {
        "type": "livre", "auteurs": [{"nom": "Martin", "prenom": "Anne"}], "annee": "2020",
        "titre": "La culture pour tous", "champs": {"editeur": "Seuil"}})
    source = vue["cree"]
    statut, vue = client("POST", f"/api/sources/{source}/extraits", {
        "texte": "La culture est un droit.", "page_debut": "45", "nature": "citation"})
    assert statut == 200
    e = next(x for x in vue["extraits"] if x["id"] == vue["cree"])
    assert e["citation"]["texte"] == "(Martin, 2020, p. 45)"
    assert e["narrative"]["texte"] == "Martin (2020, p. 45)"
    assert e["avec_texte"]["texte"] == "« La culture est un droit. » (Martin, 2020, p. 45)"

    # Citation sans page : refusée avec un message qui dit quoi faire.
    statut, erreur = client("PATCH", f"/api/extraits/{e['id']}", {"page_debut": ""})
    assert statut == 400 and "numéro de page" in erreur["erreur"]

    statut, vue = client("PATCH", f"/api/extraits/{e['id']}", {"nature": "idee_perso", "integre": True})
    e = vue["extraits"][0]
    assert e["integre"] and "citation" not in e  # une idée personnelle ne se cite pas

    statut, vue = client("DELETE", f"/api/extraits/{e['id']}")
    assert statut == 200 and vue["extraits"] == []


@avec_client
def test_tous_les_extraits_pour_la_grille(client):
    _, a = client("POST", "/api/sources", {"type": "livre", "auteurs": [{"nom": "Martin", "prenom": "A."}],
                                           "annee": "2020", "titre": "Alpha", "champs": {"editeur": "Seuil"}})
    _, b = client("POST", "/api/sources", {"type": "livre", "auteurs": [{"nom": "Martin", "prenom": "A."}],
                                           "annee": "2020", "titre": "Bêta", "champs": {"editeur": "Seuil"}})
    client("POST", f"/api/sources/{a['cree']}/extraits", {"texte": "Premier.", "page_debut": "3", "nature": "citation"})
    client("POST", f"/api/sources/{b['cree']}/extraits", {"texte": "Mon idée.", "nature": "idee_perso"})
    statut, grille = client("GET", "/api/extraits")
    assert statut == 200 and len(grille["extraits"]) == 2
    premier = next(e for e in grille["extraits"] if e["texte"] == "Premier.")
    # Même auteur, même année : les lettres a/b suivent l'ordre des titres, ici aussi.
    assert premier["citation"]["texte"] == "(Martin, 2020a, p. 3)"
    assert grille["sources"][b["cree"]]["etiquette"] == "Martin (2020b)"
    assert grille["sources"][a["cree"]]["reference"]["html"] == "Martin, A. (2020a). <i>Alpha</i>. Seuil."
    idee = next(e for e in grille["extraits"] if e["nature"] == "idee_perso")
    assert "citation" not in idee


@avec_client
def test_bibliographie_seulement_les_sources_citees(client):
    def source(**donnees):
        return client("POST", "/api/sources", {"type": "livre", "champs": {"editeur": "Seuil"}, **donnees})[1]["cree"]

    integree = source(auteurs=[{"nom": "Martin", "prenom": "A."}], annee="2020", titre="Citée par un extrait")
    lue = source(auteurs=[{"nom": "Dubois", "prenom": "B."}], annee="2019", titre="Lue, pas encore citée")
    partie1 = source(auteurs=[{"nom": "Adam", "prenom": "C."}], annee="2018", titre="Citée en partie 1", citee_partie1=True)
    site = client("POST", "/api/sources", {"type": "page_web", "auteurs": [{"organisation": "UNESCO"}], "annee": "2022",
                                          "titre": "Culture", "champs": {"url": "https://unesco.org"}})[1]["cree"]
    entretien = client("POST", "/api/sources", {"type": "communication_personnelle", "auteurs": [{"nom": "Van Damme", "prenom": "E."}],
                                               "annee": "2026", "citee_partie1": True})[1]["cree"]
    client("POST", f"/api/sources/{integree}/extraits", {"texte": "a", "nature": "paraphrase", "integre": True,
                                                          "auteur_origine": {"auteurs": [{"nom": "Piaget", "prenom": ""}], "annee": "1952"}})
    client("POST", f"/api/sources/{lue}/extraits", {"texte": "b", "nature": "paraphrase"})
    client("POST", f"/api/sources/{site}/extraits", {"texte": "c", "nature": "paraphrase", "integre": True})
    client("POST", f"/api/sources/{entretien}/extraits", {"texte": "d", "nature": "paraphrase", "integre": True})

    statut, b = client("GET", "/api/bibliographie")
    assert statut == 200 and b["decoupage"] == "une_liste"  # nouveau mémoire : la liste unique de l'APA
    assert [s["titre"] for s in b["sections"]] == ["Références"]
    assert [x["id"] for x in b["sections"][0]["references"]] == [partie1, integree, site]

    assert client("PATCH", "/api/projet", {"bibliographie": "n_importe_quoi"})[0] == 400
    client("PATCH", "/api/projet", {"bibliographie": "trois_parties"})
    statut, b = client("GET", "/api/bibliographie")
    assert [s["titre"] for s in b["sections"]] == ["Références bibliographiques", "Sitographie"]
    scientifiques = b["sections"][0]["references"]
    assert [x["id"] for x in scientifiques] == [partie1, integree]  # ordre alphabétique ; ni Dubois ni l'entretien
    assert [x["raison"] for x in scientifiques] == ["déjà citée", "1 extrait intégré"]
    assert "Piaget" not in b["copie"]["texte"]  # auteur cité de seconde main : pas une source
    assert b["sections"][1]["references"][0]["manques"] == ["Consulté le (ex. 29 septembre 2026)"]
    assert b["a_completer"] == 1
    assert [x["id"] for x in b["non_incluses"]] == [lue]
    assert b["copie"]["html"].startswith("<p><strong>Références bibliographiques</strong></p><p>Adam, C. (2018). "
                                         "<i>Citée en partie 1</i>. Seuil.</p>")
    assert b["copie"]["texte"].startswith("Références bibliographiques\n\nAdam, C. (2018). Citée en partie 1. Seuil.\n"
                                          "Martin, A. (2020).")
    assert "\n\nSitographie\n\nUNESCO. (2022)." in b["copie"]["texte"]


@avec_client
def test_supprimer_une_source_demande_confirmation(client):
    _, vue = client("POST", "/api/sources", {"type": "livre", "titre": "T"})
    source = vue["cree"]
    client("POST", f"/api/sources/{source}/extraits", {"texte": "x", "nature": "paraphrase"})
    statut, reponse = client("DELETE", f"/api/sources/{source}")
    assert statut == 409 and "1 extrait" in reponse["confirmation"]
    statut, liste = client("DELETE", f"/api/sources/{source}?confirme=1")
    assert statut == 200 and liste["sources"] == []


@avec_client
def test_donnees_mal_formees_refusees(client):
    _, vue = client("POST", "/api/sources", {"type": "livre"})
    source = vue["cree"]
    for corps, attendu in (({"auteurs": "Martin"}, "Auteurs"),
                           ({"auteurs": [{"nom": 3}]}, "Auteurs"),
                           ({"type": "roman"}, "Type de source inconnu"),
                           ({"provenance": "saisie"}, "non modifiable"),
                           ({"citee_partie1": "oui"}, "oui ou non")):
        statut, erreur = client("PATCH", f"/api/sources/{source}", corps)
        assert statut == 400 and attendu in erreur["erreur"], (corps, erreur)
    statut, erreur = client("POST", f"/api/sources/{source}/extraits", {"texte": "x", "nature": "paraphrase",
                                                                       "mots_cles": ["inexistant"]})
    assert statut == 400
    _, relue = client("GET", f"/api/sources/{source}")
    assert relue["extraits"] == [] and relue["source"]["auteurs"] == []


if __name__ == "__main__":
    lancer(globals())
