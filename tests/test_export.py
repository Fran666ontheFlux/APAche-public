import urllib.request

from outils import lancer

from memoire import export
from memoire.modele import Source
from test_sources_serveur import avec_client

ARRIETA = Source(type="article_revue", auteurs=[{"nom": "Arrieta", "prenom": "X."}], annee="2017",
                titre="Rooftop beekeeping transformations",
                champs={"revue": "Green Studies", "volume": "54", "numero": "4", "pages": "953–970",
                        "doi": "https://doi.org/10.9999/0042098016630507"})
VERNIER = Source(type="chapitre", auteurs=[{"nom": "Vernier", "prenom": "M."}], annee="2019",
                 titre="Les espaces de construction du collectif",
                 champs={"directeurs": [{"nom": "Fabbri", "prenom": "I."}], "titre_ouvrage": "Pratiques du collectif",
                         "pages": "29-43", "editeur": "Éditions du Semis"})
LUMEN = Source(type="article_revue", auteurs=[{"organisation": "Lumen"}], annee="2017",
                 titre="Pour une histoire sensible des toits", champs={"revue": "Espaces & Conflits", "volume": "105-106"})


def test_ris():
    texte = export.ris([ARRIETA, VERNIER])
    lignes = texte.split("\r\n")
    assert lignes[:4] == ["TY  - JOUR", "AU  - Arrieta, X.", "TI  - Rooftop beekeeping transformations",
                          "T2  - Green Studies"]
    for attendu in ("PY  - 2017", "VL  - 54", "IS  - 4", "SP  - 953", "EP  - 970", "DO  - 10.9999/0042098016630507",
                    "TY  - CHAP", "ED  - Fabbri, I.", "T2  - Pratiques du collectif", "PB  - Éditions du Semis"):
        assert attendu in lignes, attendu
    assert lignes.count("ER  - ") == 2


def test_bibtex():
    texte = export.bibtex([ARRIETA, VERNIER, LUMEN, Source(type="article_revue", auteurs=[{"nom": "Arrieta"}], annee="2017", titre="Autre")])
    assert "@article{arrieta2017,\n  author = {Arrieta, X.},\n  title = {{Rooftop beekeeping transformations}}," in texte
    assert "  pages = {953--970}," in texte and "  doi = {10.9999/0042098016630507}" in texte
    assert "@incollection{vernier2019," in texte and "  editor = {Fabbri, I.}," in texte and "  booktitle = {Pratiques du collectif}," in texte
    assert "author = {{Lumen}}" in texte  # une organisation n'est pas « Nom, Prénom »
    assert "journal = {Espaces \\& Conflits}" in texte  # caractères spéciaux de LaTeX protégés
    assert "@article{arrieta2017a," in texte  # deux fois la même clé : la seconde est distinguée


@avec_client
def test_par_le_serveur(client):
    cite = client("POST", "/api/sources", {"type": "livre", "auteurs": [{"nom": "Adam", "prenom": "C."}], "annee": "2018",
                                           "titre": "Citée", "champs": {"editeur": "E"}, "citee_partie1": True})[1]["cree"]
    client("POST", "/api/sources", {"type": "livre", "auteurs": [{"nom": "Zola", "prenom": "E."}], "titre": "Pas citée",
                                    "champs": {"editeur": "E"}})
    base = f"http://127.0.0.1:{client.port}/api/export"
    with urllib.request.urlopen(f"{base}?format=ris") as r:
        assert r.headers["Content-Disposition"] == 'attachment; filename="memoire-citees.ris"'
        texte = r.read().decode("utf-8")
    assert "AU  - Adam, C." in texte and "Zola" not in texte  # par défaut : les sources citées seulement
    with urllib.request.urlopen(f"{base}?format=bibtex&sources=toutes") as r:
        texte = r.read().decode("utf-8")
    assert "adam2018" in texte and "zola" in texte
    try:
        urllib.request.urlopen(f"{base}?format=docx")
        raise AssertionError("format inconnu accepté")
    except urllib.error.HTTPError as e:
        assert e.code == 400
    assert cite


if __name__ == "__main__":
    lancer(globals())
