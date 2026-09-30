from pathlib import Path

from outils import dossier_temporaire, lancer

from memoire import fichiers, recherche
from memoire.depot import Memoire
from memoire.modele import DonneesInvalides, Source
from test_fichiers import ARTICLE, pdf
from test_sources_serveur import avec_client


def _memoire(d):
    m = Memoire.ouvrir(Path(d))
    arrieta = m.ajouter_source(Source(type="article_revue", auteurs=[{"nom": "Arrieta", "prenom": "X."}], annee="2017",
                                     titre="Rooftop", champs={"revue": "Green Studies"}))
    m.joindre_fichier(arrieta.id, "arrieta.pdf", pdf(ARTICLE))  # pages imprimées 953-955
    prades = m.ajouter_source(Source(type="article_revue", auteurs=[{"nom": "Prades", "prenom": "B."}], annee="2013",
                                     titre="Rythmes", champs={"revue": "Loisir et Société"}))
    m.joindre_fichier(prades.id, "prades.pdf", pdf([["Les récoltes échelonnées du potager."],
                                                   ["Une fête des semences transforme l'espace public."]]))
    return m, arrieta, prades


def test_lecture_puis_recherche():
    with dossier_temporaire() as d:
        m, arrieta, prades = _memoire(d)
        fichiers._cache.clear()
        assert recherche.rechercher(m, "greening")["non_lus"] == 2  # rien de lu : rien de trouvé, et il le dit
        etat = recherche.indexer(m)
        assert (etat["total"], etat["restants"], etat["illisibles"]) == (2, 0, [])
        assert len(list((Path(d) / "index").glob("*.json"))) == 2  # le texte est gardé dans le dossier de données

        r = recherche.rechercher(m, "GREENING expeditionary")  # deux mots, sur la même page
        [x] = r["resultats"]
        assert (x["etiquette"], x["page"], r["non_lus"]) == ("Arrieta (2017)", "954", 0)
        assert [x["passage"][a:b] for a, b in x["surlignes"]] == ["expeditionary", "greening"]

        # Accents et majuscules ne comptent pas.
        [y] = recherche.rechercher(m, "echelonnees")["resultats"]
        assert y["etiquette"] == "Prades (2013)" and y["passage"][slice(*y["surlignes"][0])] == "échelonnées"
        # Deux mots sur deux pages différentes : pas un résultat.
        assert recherche.rechercher(m, "récoltes fête")["resultats"] == []
        m.fermer()


def test_texte_garde_d_une_seance_a_l_autre():
    with dossier_temporaire() as d:
        m, arrieta, _ = _memoire(d)
        recherche.indexer(m)
        fichiers._cache.clear()  # comme au lancement suivant de l'outil
        lu_avant = fichiers._lire_pdf
        fichiers._lire_pdf = lambda chemin: (_ for _ in ()).throw(AssertionError("PDF relu inutilement"))
        try:
            assert recherche.rechercher(m, "expeditionary")["resultats"]  # lu depuis index/, sans relire le PDF
        finally:
            fichiers._lire_pdf = lu_avant
        # Un fichier remplacé est relu : son texte n'est plus le même.
        m.joindre_fichier(arrieta.id, "arrieta-v2.pdf", pdf([["Version corrigée avec un mot nouveau : palimpseste."]]))
        assert recherche.indexer(m)["restants"] == 0
        assert recherche.rechercher(m, "palimpseste")["resultats"][0]["etiquette"] == "Arrieta (2017)"
        assert not recherche.rechercher(m, "expeditionary")["resultats"]
        m.fermer()


def test_fichier_illisible_ne_bloque_pas_les_autres():
    with dossier_temporaire() as d:
        m, arrieta, _ = _memoire(d)
        abime = m.ajouter_source(Source(type="livre", titre="Abîmé", champs={"editeur": "E"}))
        m.joindre_fichier(abime.id, "abime.pdf", b"%PDF-1.4\n pas vraiment un PDF")
        etat = recherche.indexer(m)
        assert etat["illisibles"] == [abime.id] and etat["restants"] == 0
        assert recherche.rechercher(m, "expeditionary")["resultats"]
        m.fermer()


def test_budget_de_lecture_et_requete_vide():
    with dossier_temporaire() as d:
        m, *_ = _memoire(d)
        fichiers._cache.clear()
        budget = recherche.BUDGET_LECTURE
        recherche.BUDGET_LECTURE = -1  # plus de temps du tout : rien n'est lu, tout reste à lire
        try:
            assert recherche.indexer(m)["restants"] == 2
        finally:
            recherche.BUDGET_LECTURE = budget
        for vide in ("", "a", "  "):
            try:
                recherche.rechercher(m, vide)
                raise AssertionError(repr(vide))
            except DonneesInvalides:
                pass
        m.fermer()


@avec_client
def test_par_le_serveur(client):
    _, vue = client("POST", "/api/sources", {"type": "livre", "titre": "T", "champs": {"editeur": "E"}})
    from test_fichiers import envoyer
    envoyer(client, vue["cree"], "t.pdf", pdf(ARTICLE))
    statut, etat = client("POST", "/api/recherche/indexer")
    assert statut == 200 and etat["restants"] == 0
    statut, r = client("GET", "/api/recherche?q=expeditionary%20force")
    assert statut == 200 and r["resultats"][0]["page"] == "954"
    statut, erreur = client("GET", "/api/recherche?q=")
    assert statut == 400 and "deux lettres" in erreur["erreur"]


if __name__ == "__main__":
    lancer(globals())
