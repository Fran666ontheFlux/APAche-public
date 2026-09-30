from pathlib import Path

from outils import dossier_temporaire, lancer

from memoire import suggestions as sg
from memoire.depot import Memoire
from memoire.modele import Extrait, Source
from test_sources_serveur import avec_client


def test_formes_d_un_meme_mot_ramenees_a_la_meme_racine():
    # Ce qui compte n'est pas la racine exacte, mais que les formes d'un mot se rejoignent.
    familles = [("culturel", "culturelle", "culturels", "culturelles"), ("rue", "rues"), ("collectif", "collective", "collectives"),
                ("territorial", "territoriaux"), ("créateur", "créatrice", "créatrices"), ("urbain", "urbaines"),
                ("musée", "Musées", "MUSEE"), ("study", "studies"), ("jardin", "jardins")]
    for famille in familles:
        assert len({sg.racine(m) for m in famille}) == 1, {m: sg.racine(m) for m in famille}
    assert sg.racine("culture") != sg.racine("culte")


def _memoire(d):
    m = Memoire.ouvrir(Path(d))
    ville = m.ajouter_mot_cle("Ville", synonymes=["urbain", "métropole"])
    quartier = m.ajouter_mot_cle("Vie de quartier", parent_id=ville.id, synonymes=["rue", "streetlife"])
    compost = m.ajouter_mot_cle("Compost collectif", synonymes=["compostage partagé"])
    art = m.ajouter_mot_cle("Art")
    return m, ville, quartier, compost, art


def ids(m, texte):
    return {s["libelle"] for s in sg.suggerer(m, texte)}


def test_synonymes_pluriels_feminins_et_accents():
    with dossier_temporaire() as d:
        m, *_ = _memoire(d)
        assert ids(m, "Les politiques URBAINES et les rues fleuries des métropoles.") == {"Ville", "Vie de quartier"}
        assert ids(m, "Streetlife in the city") == {"Vie de quartier"}
        m.fermer()


def test_expression_de_plusieurs_mots_dans_n_importe_quel_ordre():
    with dossier_temporaire() as d:
        m, *_ = _memoire(d)
        assert ids(m, "Un compost, forcément collectif, du quartier.") == {"Compost collectif"}
        assert ids(m, "Le compostage dit partagé.") == {"Compost collectif"}
        assert ids(m, "Un compost individuel.") == set()  # un seul des deux mots : pas assez
        m.fermer()


def test_pas_de_fausse_piste_sur_un_mot_court():
    with dossier_temporaire() as d:
        m, *_ = _memoire(d)
        # « art » ne se reconnaît que seul : pas dans « partie », « artiste » ni « quartier ».
        assert ids(m, "Une partie des artistes du quartier.") == set()
        assert ids(m, "L'art contemporain.") == {"Art"}
        m.fermer()


def test_passages_pour_le_surlignage():
    with dossier_temporaire() as d:
        m, *_ = _memoire(d)
        texte = "La rue urbaine."
        s = {x["libelle"]: x for x in sg.suggerer(m, texte)}
        assert [texte[a:b] for a, b in s["Vie de quartier"]["passages"]] == ["rue"]
        assert [texte[a:b] for a, b in s["Ville"]["passages"]] == ["urbaine"]
        assert s["Ville"]["termes"] == ["urbaine"]
        m.fermer()


def test_mesure_sur_les_extraits_classes():
    with dossier_temporaire() as d:
        m, ville, quartier, compost, art = _memoire(d)
        source = m.ajouter_source(Source(type="livre", titre="T"))
        for texte, mots in (("La rue en ville.", [ville.id]),                 # rue (sous-thème de Ville) : juste
                            ("Un potager d'école.", [compost.id]),         # rien trouvé : oublié
                            ("L'art et la métropole.", [art.id]),              # Art juste, Ville en trop
                            ("Pas encore classé.", [])):                       # ignoré
            m.ajouter_extrait(Extrait(source_id=source.id, texte=texte, nature="paraphrase", mots_cles=mots))
        mesure = sg.mesurer(m)
        # Proposés (au niveau des thèmes) : Ville ; rien ; Art + Ville → 3, dont 2 justes.
        # Posés : 3, retrouvés : 2.
        assert mesure == {"extraits": 3, "justes": 67, "retrouves": 67, "proposes": 3}
        m.fermer()


@avec_client
def test_par_le_serveur(client):
    client("POST", "/api/mots-cles", {"libelle": "Jardin", "synonymes": ["reconversion"]})
    statut, r = client("POST", "/api/suggestions", {"texte": "La reconversion des jardins partagés."})
    assert statut == 200 and [s["libelle"] for s in r["suggestions"]] == ["Jardin"]
    statut, mesure = client("GET", "/api/mots-cles/mesure")
    assert statut == 200 and mesure["extraits"] == 0 and mesure["justes"] is None


if __name__ == "__main__":
    lancer(globals())
