from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from outils import dossier_temporaire, lancer

from memoire import sauvegardes, verrou
from memoire.stockage import ecrire_json
from memoire.verrou import MemoireDejaOuvert


def _verrou_d_un_autre_pc(dossier, depuis="2026-10-05T14:02:00"):
    ecrire_json(Path(dossier) / verrou.NOM_FICHIER, {"pc": "PORTABLE", "depuis": depuis})


def test_prendre_puis_rendre():
    with dossier_temporaire() as d:
        verrou.prendre(Path(d))
        assert verrou.lire(Path(d))["pc"] == verrou.nom_pc()
        verrou.rendre(Path(d))
        assert verrou.lire(Path(d)) is None


def test_verrou_d_un_autre_pc_bloque_avec_message_clair():
    with dossier_temporaire() as d:
        _verrou_d_un_autre_pc(d)
        try:
            verrou.prendre(Path(d))
        except MemoireDejaOuvert as e:
            assert e.pc == "PORTABLE"
        else:
            raise AssertionError("MemoireDejaOuvert attendue")


def test_message_du_verrou():
    depuis = datetime(2026, 10, 5, 14, 2)
    assert verrou.message_verrou("PORTABLE", depuis, aujourd_hui=depuis) == (
        "Le mémoire semble ouvert sur PORTABLE depuis 14 h 02. Ferme-le là-bas, "
        "ou attends la fin de la synchronisation (Google Drive, OneDrive…)."
    )


def test_message_precise_la_date_si_ce_n_est_pas_aujourd_hui():
    depuis = datetime(2026, 10, 5, 9, 30)
    message = verrou.message_verrou("PORTABLE", depuis, aujourd_hui=depuis + timedelta(days=2))
    assert "depuis le 05/10 à 9 h 30" in message


def test_ouvrir_quand_meme():
    with dossier_temporaire() as d:
        _verrou_d_un_autre_pc(d)
        verrou.prendre(Path(d), forcer=True)
        assert verrou.lire(Path(d))["pc"] == verrou.nom_pc()


def test_verrou_laisse_par_ce_pc_est_repris():
    with dossier_temporaire() as d:
        ecrire_json(Path(d) / verrou.NOM_FICHIER, {"pc": verrou.nom_pc(), "depuis": "2026-01-01T00:00:00"})
        verrou.prendre(Path(d))


def test_rendre_ne_supprime_pas_le_verrou_de_l_autre_pc():
    with dossier_temporaire() as d:
        _verrou_d_un_autre_pc(d)
        verrou.rendre(Path(d))
        assert verrou.lire(Path(d))["pc"] == "PORTABLE"


def test_sauvegarde_datee_et_limite_a_30():
    with dossier_temporaire() as d:
        fichier = Path(d) / "memoire.json"
        fichier.write_text("{}")
        debut = datetime(2026, 10, 1, 8, 0, 0)
        for i in range(35):
            sauvegardes.sauvegarder(fichier, debut + timedelta(hours=i))
        restantes = sauvegardes.lister(Path(d))
        assert len(restantes) == 30
        assert restantes[0].name == "memoire_2026-10-01_13-00-00.json", "les plus anciennes partent"
        assert restantes[-1].name == "memoire_2026-10-02_18-00-00.json"


def test_purge_ignore_les_fichiers_de_l_utilisateur():
    with dossier_temporaire() as d:
        rep = Path(d) / sauvegardes.NOM_DOSSIER
        rep.mkdir()
        (rep / "ma copie à garder.json").write_text("{}")
        sauvegardes.purger(Path(d), a_garder=0)
        assert (rep / "ma copie à garder.json").exists()


def test_sauvegarde_quotidienne_une_seule_fois_par_jour():
    with dossier_temporaire() as d:
        fichier = Path(d) / "memoire.json"
        fichier.write_text("{}")
        matin = datetime(2026, 10, 1, 8, 0)
        assert sauvegardes.sauvegarde_quotidienne(fichier, matin) is not None
        assert sauvegardes.sauvegarde_quotidienne(fichier, matin.replace(hour=17)) is None
        assert sauvegardes.sauvegarde_quotidienne(fichier, matin + timedelta(days=1)) is not None


def test_pas_de_sauvegarde_sans_donnees():
    with dossier_temporaire() as d:
        assert sauvegardes.sauvegarder(Path(d) / "memoire.json") is None


def test_detection_des_conflits_drive():
    with dossier_temporaire() as d:
        for nom in ("memoire.json", "verrou.json", "memoire (1).json",
                    "Conflict copy of notes.txt", "verrou (1).json", "article.pdf"):
            (Path(d) / nom).write_text("{}")
        (Path(d) / ".ecriture-memoire.json-abc").write_text("{}")
        trouves = [p.name for p in sauvegardes.detecter_conflits(Path(d), ("memoire.json", "verrou.json"))]
        assert trouves == ["Conflict copy of notes.txt", "memoire (1).json", "verrou (1).json"]


def test_nom_pc_repli_sur_le_nom_reseau():
    with mock.patch.dict("os.environ", {"COMPUTERNAME": ""}), \
            mock.patch.object(verrou.socket, "gethostname", return_value="FIXE"):
        assert verrou.nom_pc() == "FIXE"


def test_jamais_ecraser_ce_qu_un_autre_pc_a_ecrit():
    """Portable resté ouvert ; l'autre PC a ajouté des données, que Drive a synchronisées ici."""
    import json

    from memoire.depot import Memoire
    from memoire.stockage import ErreurStockage

    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        m.ajouter_mot_cle("Végétalisation")
        fichier = Path(d) / "memoire.json"
        ecrit_ailleurs = json.loads(fichier.read_text(encoding="utf-8"))
        ecrit_ailleurs["mots_cles"].append({"id": "autrepc00001", "libelle": "Ajouté sur l'autre PC"})
        fichier.write_text(json.dumps(ecrit_ailleurs, ensure_ascii=False), encoding="utf-8")
        try:
            m.ajouter_mot_cle("Jardins")
            raise AssertionError("aurait dû refuser d'écraser")
        except ErreurStockage as e:
            assert "Ferme APAche" in str(e) and "memoire_conflit_" in str(e)
        assert "Ajouté sur l'autre PC" in fichier.read_text(encoding="utf-8")  # rien d'écrasé
        conflits = list((Path(d) / "sauvegardes").glob("memoire_conflit_*.json"))
        assert len(conflits) == 1 and "Jardins" in conflits[0].read_text(encoding="utf-8")  # rien de perdu non plus
        m.fermer()


def test_verrou_repris_ailleurs_bloque_l_ecriture():
    from memoire.depot import Memoire
    from memoire.stockage import ErreurStockage

    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        _verrou_d_un_autre_pc(d)  # « Ouvrir quand même » sur le portable
        try:
            m.ajouter_mot_cle("Jardins")
            raise AssertionError("aurait dû refuser")
        except ErreurStockage as e:
            assert "PORTABLE" in str(e)


def test_fichier_reecrit_a_l_identique_par_drive_n_est_pas_un_conflit():
    import os

    from memoire.depot import Memoire

    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        m.ajouter_mot_cle("Végétalisation")
        fichier = Path(d) / "memoire.json"
        fichier.write_bytes(fichier.read_bytes())  # même contenu, nouvelle date
        os.utime(fichier, None)
        m.ajouter_mot_cle("Jardins")  # pas d'erreur
        assert "Jardins" in fichier.read_text(encoding="utf-8")
        m.fermer()


if __name__ == "__main__":
    lancer(globals())
