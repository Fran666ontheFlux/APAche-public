"""Gras et italique dans le texte d'un extrait."""

from pathlib import Path

from outils import dossier_temporaire, lancer

from memoire import mise_en_forme, suggestions, vues
from memoire.depot import Memoire
from memoire.modele import Extrait, Source


def test_texte_simple_inchange():
    for texte in ("Un passage ordinaire.", "a < b et c > d", "R&D, <br> et <u>souligné</u>", ""):
        assert mise_en_forme.nettoyer(texte) == texte
        assert mise_en_forme.brut(texte) == texte


def test_forme_canonique():
    n = mise_en_forme.nettoyer
    assert n("<b>un</b><b> mot</b>") == "<b>un mot</b>"  # morceaux voisins réunis
    assert n("a <b></b>b <i> </i>c") == "a b  c"  # balises vides ou sur une espace retirées
    assert n("<b>gras <i>et italique</i></b> fin") == "<b>gras <i>et italique</i></b> fin"
    assert n("</b>orpheline <i>ouverte") == "orpheline <i>ouverte</i>"  # toujours équilibré
    assert mise_en_forme.brut("<b>gras <i>et italique</i></b>") == "gras et italique"


def test_html_pour_google_docs():
    assert mise_en_forme.vers_html("<i>Le Capital</i> & <b>R&D</b> <3") == "<i>Le Capital</i> &amp; <b>R&amp;D</b> &lt;3"


def test_extrait_enregistre_et_copie_avec_sa_mise_en_forme():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        mot = m.ajouter_mot_cle("Jardins partagés")
        s = m.ajouter_source(Source(type="livre", auteurs=[{"nom": "Martin", "prenom": "Léa"}], annee="2020",
                                    titre="Les jardins", champs={"editeur": "PUF"}))
        e = m.ajouter_extrait(Extrait(source_id=s.id, page_debut="45",
                                      texte="Les <b>jardins</b><b> partagés</b> selon <i>Le Monde</i>."))
        assert e.texte == "Les <b>jardins partagés</b> selon <i>Le Monde</i>."
        vue = next(x for x in vues.vue_extraits(m)["extraits"] if x["id"] == e.id)
        assert vue["avec_texte"]["texte"] == "« Les jardins partagés selon Le Monde. » (Martin, 2020, p. 45)"
        assert vue["avec_texte"]["html"].startswith("« Les <b>jardins partagés</b> selon <i>Le Monde</i>. » (Martin")
        # Les suggestions lisent le texte sans balises : « jardins partagés » est reconnu.
        assert [x["id"] for x in suggestions.suggerer(m, mise_en_forme.brut(e.texte))] == [mot.id]
        m.fermer()


if __name__ == "__main__":
    lancer(globals())
