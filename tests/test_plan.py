from pathlib import Path

from outils import dossier_temporaire, lancer

from memoire import vues
from memoire.depot import ConfirmationRequise, Memoire
from memoire.modele import DonneesInvalides, Extrait, Source
from test_sources_serveur import avec_client


def _memoire(d):
    m = Memoire.ouvrir(Path(d))
    ville = m.ajouter_mot_cle("Ville")
    quartier = m.ajouter_mot_cle("Vie de quartier", parent_id=ville.id)
    jardin = m.ajouter_mot_cle("Jardins")
    source = m.ajouter_source(Source(type="livre", auteurs=[{"nom": "Martin", "prenom": "A."}], annee="2020", titre="T",
                                     champs={"editeur": "E"}))
    return m, ville, quartier, jardin, source


def test_numerotation_et_deplacement():
    with dossier_temporaire() as d:
        m, *_ = _memoire(d)
        intro = m.ajouter_section("Introduction")
        ch1 = m.ajouter_section("La rue, un enjeu public")
        s11 = m.ajouter_section("Politiques de la rue", niveau=2)
        ch2 = m.ajouter_section("Les jardins")
        s12 = m.ajouter_section("Les acteurs", niveau=2, apres=s11.id)  # insérée après 1.1, avant le chapitre 2
        titres = lambda: [(m.numeros_du_plan()[s.id], s.titre) for s in m.plan]
        assert titres() == [("1", "Introduction"), ("2", "La rue, un enjeu public"), ("2.1", "Politiques de la rue"),
                            ("2.2", "Les acteurs"), ("3", "Les jardins")]
        # Un chapitre monte avec ses sections, par-dessus le chapitre entier qui le précède.
        m.deplacer_section(ch2.id, "haut")
        assert titres() == [("1", "Introduction"), ("2", "Les jardins"), ("3", "La rue, un enjeu public"),
                            ("3.1", "Politiques de la rue"), ("3.2", "Les acteurs")]
        m.deplacer_section(ch1.id, "haut")  # le chapitre 3 et ses deux sections passent devant « Les jardins »
        assert [t for _, t in titres()] == ["Introduction", "La rue, un enjeu public", "Politiques de la rue",
                                            "Les acteurs", "Les jardins"]
        m.deplacer_section(ch1.id, "bas")   # et redescendent d'un bloc
        assert [t for _, t in titres()][1:3] == ["Les jardins", "La rue, un enjeu public"]
        m.deplacer_section(intro.id, "haut")  # déjà en tête : rien ne bouge
        assert titres()[0] == ("1", "Introduction")
        # Une section, elle, peut changer de chapitre.
        m.deplacer_section(s11.id, "haut")
        assert titres()[2] == ("2.1", "Politiques de la rue")
        try:
            m.deplacer_section(s11.id, "gauche")
            raise AssertionError("sens inconnu accepté")
        except DonneesInvalides:
            pass
        m.modifier_section(intro.id, niveau=2)  # une section avant tout chapitre
        assert m.numeros_du_plan()[intro.id] == "0.1"
        m.fermer()
        relu = Memoire.ouvrir(Path(d))  # le plan est bien enregistré, dans l'ordre
        assert [s.titre for s in relu.plan] == ["Introduction", "Les jardins", "Politiques de la rue",
                                                "La rue, un enjeu public", "Les acteurs"]
        relu.fermer()


def test_donnees_du_plan_verifiees():
    with dossier_temporaire() as d:
        m, *_ = _memoire(d)
        s = m.ajouter_section("Chapitre")
        for changement, attendu in (({"titre": "  "}, "titre"), ({"niveau": 3}, "chapitre ou une section"),
                                    ({"mots_cles": ["inexistant"]}, "n'existe plus"), ({"couleur": "rouge"}, "non modifiable")):
            try:
                m.modifier_section(s.id, **changement)
                raise AssertionError(changement)
            except DonneesInvalides as e:
                assert attendu in str(e), (changement, e)
        assert m.plan[0].titre == "Chapitre" and m.plan[0].niveau == 1  # rien n'a changé
        m.fermer()


def test_extraits_d_une_partie():
    with dossier_temporaire() as d:
        m, ville, quartier, jardin, source = _memoire(d)
        ajouter = lambda texte, mots, integre=False: m.ajouter_extrait(
            Extrait(source_id=source.id, texte=texte, nature="paraphrase", mots_cles=mots, integre=integre))
        deja = ajouter("Déjà dans le mémoire.", [ville.id], integre=True)
        ajouter("Sur la rue.", [quartier.id])              # sous-thème de Ville : compte pour Ville
        ajouter("Sur les jardins.", [jardin.id])
        a_la_main = ajouter("Rangé à la main.", [])
        chapitre = m.ajouter_section("La ville", mots_cles=[ville.id])
        m.modifier_extrait(a_la_main.id, section_plan=chapitre.id)

        vue = vues.vue_section(m, chapitre.id)
        assert [e["texte"] for e in vue["extraits"]] == ["Sur la rue.", "Rangé à la main.", "Déjà dans le mémoire."]
        assert [e["a_la_main"] for e in vue["extraits"]] == [False, True, False]
        assert vue["extraits"][0]["citation"]["texte"] == "(Martin, 2020)"
        assert set(vue["sources"]) == {source.id}
        plan = vues.vue_plan(m)["sections"][0]
        assert (plan["numero"], plan["nb_extraits"], plan["nb_a_integrer"]) == ("1", 3, 2)
        assert deja.integre
        m.fermer()


def test_supprimer_une_partie_et_mots_cles_supprimes():
    with dossier_temporaire() as d:
        m, ville, quartier, jardin, source = _memoire(d)
        partie = m.ajouter_section("Partie", mots_cles=[ville.id, jardin.id])
        e = m.ajouter_extrait(Extrait(source_id=source.id, texte="x", nature="paraphrase", section_plan=partie.id))
        # Supprimer un mot-clé l'enlève du plan ; fusionner le remplace.
        m.supprimer_mot_cle(jardin.id)
        assert m.plan[0].mots_cles == [ville.id]
        autre = m.ajouter_mot_cle("Urbain")
        m.modifier_section(partie.id, mots_cles=[ville.id, autre.id])
        m.fusionner_mots_cles(ville.id, autre.id)
        assert m.plan[0].mots_cles == [ville.id]
        try:
            m.supprimer_section(partie.id)
            raise AssertionError("aurait dû demander confirmation")
        except ConfirmationRequise as c:
            assert "1 extrait" in str(c) and "restent dans la grille" in str(c)
        m.supprimer_section(partie.id, confirme=True)
        assert not m.plan and m.extraits[e.id].section_plan is None and e.id in m.extraits
        try:
            m.modifier_extrait(e.id, section_plan="inexistante")
            raise AssertionError("partie inexistante acceptée")
        except DonneesInvalides:
            pass
        m.fermer()


@avec_client
def test_par_le_serveur(client):
    _, projet = client("POST", "/api/mots-cles", {"libelle": "Ville"})
    ville = projet["cree"]
    statut, plan = client("POST", "/api/plan", {"titre": "La ville", "mots_cles": [ville]})
    assert statut == 200 and plan["sections"][0]["numero"] == "1"
    chapitre = plan["cree"]
    _, plan = client("POST", "/api/plan", {"titre": "Sous-partie", "niveau": 2, "apres": chapitre})
    assert [s["numero"] for s in plan["sections"]] == ["1", "1.1"]
    _, plan = client("POST", f"/api/plan/{plan['cree']}/deplacer", {"sens": "haut"})
    assert [s["titre"] for s in plan["sections"]] == ["Sous-partie", "La ville"]
    statut, _ = client("POST", f"/api/plan/{chapitre}/deplacer", {"sens": 3})
    assert statut == 400
    statut, section = client("GET", f"/api/plan/{chapitre}")
    assert statut == 200 and section["section"]["titre"] == "La ville" and section["extraits"] == []
    statut, plan = client("DELETE", f"/api/plan/{chapitre}")
    assert statut == 200 and [s["titre"] for s in plan["sections"]] == ["Sous-partie"]


if __name__ == "__main__":
    lancer(globals())
