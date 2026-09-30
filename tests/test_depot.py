import json
from pathlib import Path

from outils import dossier_temporaire, lancer

from memoire import sauvegardes, verrou
from memoire.depot import ConfirmationRequise, Memoire
from memoire.modele import DonneesInvalides, Extrait, Source
from memoire.stockage import ErreurStockage, ecrire_json


def _memoire_avec_contenu(d):
    m = Memoire.ouvrir(Path(d))
    theme = m.ajouter_mot_cle("Politiques culturelles", couleur="#6b8afd")
    sous = m.ajouter_mot_cle("Démocratisation", parent_id=theme.id, synonymes=["accès à la culture"])
    source = m.ajouter_source(Source(type="livre", auteurs=[{"nom": "Martin", "prenom": "Anne"}],
                                     annee="2020", titre="La culture pour tous"))
    extrait = m.ajouter_extrait(Extrait(source_id=source.id, texte="Un passage.", page_debut="45",
                                        mots_cles=[sous.id]))
    return m, theme, sous, source, extrait


def test_aller_retour_complet():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        m.projet.titre = "Mémoire"
        m.enregistrer()
        m.fermer()
        m2 = Memoire.ouvrir(Path(d))
        assert m2.projet.titre == "Mémoire"
        assert m2.projet.reglages_apa.conjonction == "et"
        assert m2.mots_cles[sous.id].parent_id == theme.id
        assert m2.sources[source.id].auteurs == [{"nom": "Martin", "prenom": "Anne"}]
        assert m2.extraits[extrait.id].mots_cles == [sous.id]


def test_champs_inconnus_conserves():
    # Une version plus récente de l'outil, sur l'autre PC, a pu ajouter des champs.
    with dossier_temporaire() as d:
        ecrire_json(Path(d) / "memoire.json", {
            "version_schema": 1, "futur": {"x": 1},
            "sources": [{"id": "s1", "type": "livre", "champ_futur": "garde-moi"}],
        })
        m = Memoire.ouvrir(Path(d))
        m.enregistrer()
        brut = json.loads((Path(d) / "memoire.json").read_text(encoding="utf-8"))
        assert brut["futur"] == {"x": 1}
        assert brut["sources"][0]["champ_futur"] == "garde-moi"


def test_schema_plus_recent_refuse():
    with dossier_temporaire() as d:
        ecrire_json(Path(d) / "memoire.json", {"version_schema": 999})
        try:
            Memoire.ouvrir(Path(d))
        except ErreurStockage as e:
            assert "Pull" in str(e)
        else:
            raise AssertionError("ErreurStockage attendue")
        assert verrou.lire(Path(d)) is None, "pas de verrou laissé après un échec"


def test_dossier_absent():
    with dossier_temporaire() as d:
        try:
            Memoire.ouvrir(Path(d) / "inexistant")
        except ErreurStockage as e:
            assert "Google Drive" in str(e)
        else:
            raise AssertionError("ErreurStockage attendue")


def test_ouverture_pose_le_verrou_et_fermeture_le_rend_avec_sauvegarde():
    with dossier_temporaire() as d:
        m, *_ = _memoire_avec_contenu(d)
        assert verrou.lire(Path(d)) is not None
        avant = len(sauvegardes.lister(Path(d)))
        m.fermer()
        assert verrou.lire(Path(d)) is None
        assert len(sauvegardes.lister(Path(d))) == avant + 1


def test_conflits_signales_a_l_ouverture():
    with dossier_temporaire() as d:
        (Path(d) / "memoire (1).json").write_text("{}")
        m = Memoire.ouvrir(Path(d))
        assert [p.name for p in m.conflits] == ["memoire (1).json"]


def test_renommer_un_mot_cle_ne_casse_pas_les_extraits():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        m.modifier_mot_cle(sous.id, libelle="Démocratisation culturelle")
        assert m.extraits[extrait.id].mots_cles == [sous.id]


def test_libelle_en_double_refuse():
    with dossier_temporaire() as d:
        m, *_ = _memoire_avec_contenu(d)
        try:
            m.ajouter_mot_cle("démocratisation")
        except DonneesInvalides:
            pass
        else:
            raise AssertionError("doublon accepté")


def test_hierarchie_circulaire_refusee():
    with dossier_temporaire() as d:
        m, theme, sous, *_ = _memoire_avec_contenu(d)
        try:
            m.modifier_mot_cle(theme.id, parent_id=sous.id)
        except DonneesInvalides:
            pass
        else:
            raise AssertionError("cycle accepté")


def test_suppression_d_un_mot_cle_utilise_demande_confirmation_avec_le_nombre():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        m.ajouter_extrait(Extrait(source_id=source.id, nature="paraphrase", mots_cles=[sous.id]))
        try:
            m.supprimer_mot_cle(sous.id)
        except ConfirmationRequise as e:
            assert e.nombre == 2 and "2 extraits" in str(e)
        else:
            raise AssertionError("ConfirmationRequise attendue")
        assert sous.id in m.mots_cles, "rien ne doit être supprimé sans confirmation"
        m.supprimer_mot_cle(sous.id, confirme=True)
        assert m.extraits[extrait.id].mots_cles == []


def test_suppression_d_un_theme_fait_remonter_les_sous_themes():
    with dossier_temporaire() as d:
        m, theme, sous, *_ = _memoire_avec_contenu(d)
        try:
            m.supprimer_mot_cle(theme.id)
        except ConfirmationRequise as e:
            assert "1 sous-thème" in str(e)
        else:
            raise AssertionError("ConfirmationRequise attendue")
        m.supprimer_mot_cle(theme.id, confirme=True)
        assert m.mots_cles[sous.id].parent_id is None


def test_fusion_de_mots_cles():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        acces = m.ajouter_mot_cle("Accès", synonymes=["accessibilité"])
        e2 = m.ajouter_extrait(Extrait(source_id=source.id, nature="paraphrase",
                                       mots_cles=[acces.id, sous.id]))
        m.fusionner_mots_cles(sous.id, acces.id)
        assert acces.id not in m.mots_cles
        assert m.extraits[e2.id].mots_cles == [sous.id], "sans doublon après fusion"
        assert m.mots_cles[sous.id].synonymes == ["accès à la culture", "Accès", "accessibilité"]


def test_citation_sans_page_refusee_avec_explication():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        try:
            m.ajouter_extrait(Extrait(source_id=source.id, texte="x", nature="citation"))
        except DonneesInvalides as e:
            assert "page" in str(e)
        else:
            raise AssertionError("citation sans page acceptée")


def test_modification_invalide_annulee():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        try:
            m.modifier_extrait(extrait.id, page_debut="", texte="nouveau")
        except DonneesInvalides:
            pass
        assert m.extraits[extrait.id].page_debut == "45"
        assert m.extraits[extrait.id].texte == "Un passage."


def test_extrait_vers_mot_cle_inconnu_refuse():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        try:
            m.ajouter_extrait(Extrait(source_id=source.id, nature="paraphrase", mots_cles=["zzz"]))
        except DonneesInvalides:
            pass
        else:
            raise AssertionError("mot-clé inconnu accepté")


def test_cocher_integre_est_enregistre_aussitot():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        m.modifier_extrait(extrait.id, integre=True)
        brut = json.loads((Path(d) / "memoire.json").read_text(encoding="utf-8"))
        assert brut["extraits"][0]["integre"] is True


def test_supprimer_une_source_avec_extraits_demande_confirmation():
    with dossier_temporaire() as d:
        m, theme, sous, source, extrait = _memoire_avec_contenu(d)
        try:
            m.supprimer_source(source.id)
        except ConfirmationRequise as e:
            assert e.nombre == 1
        else:
            raise AssertionError("ConfirmationRequise attendue")
        m.supprimer_source(source.id, confirme=True)
        assert not m.sources and not m.extraits


def test_type_de_source_inconnu_refuse():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        try:
            m.ajouter_source(Source(type="roman"))
        except DonneesInvalides:
            pass
        else:
            raise AssertionError("type inconnu accepté")


def test_memoire_d_avant_le_reglage_garde_ses_trois_parties():
    """Un mémoire créé avant le choix « une liste / trois parties » ne change pas de présentation ;
    un nouveau mémoire prend la liste unique de l'APA."""
    with dossier_temporaire() as d:
        ancien = Path(d) / "ancien"
        ancien.mkdir()
        (ancien / "memoire.json").write_text(json.dumps({"version_schema": 1, "projet": {"titre": "T"}}), encoding="utf-8")
        m = Memoire.ouvrir(ancien)
        assert m.projet.bibliographie == "trois_parties"
        m.fermer()
        nouveau = Path(d) / "nouveau"
        nouveau.mkdir()
        m = Memoire.ouvrir(nouveau)
        assert m.projet.bibliographie == "une_liste"
        m.ajouter_mot_cle("Thème")
        m.fermer()
        assert Memoire.ouvrir(nouveau).projet.bibliographie == "une_liste"  # enregistré : ne bascule plus


if __name__ == "__main__":
    lancer(globals())
