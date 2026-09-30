import json
import os
import time
from pathlib import Path
from unittest import mock

from outils import dossier_temporaire, lancer

from memoire import stockage
from memoire.stockage import ErreurStockage, ecrire_json, lire_json, nettoyer_temporaires


def test_aller_retour_utf8_lisible():
    with dossier_temporaire() as d:
        chemin = Path(d) / "a.json"
        ecrire_json(chemin, {"titre": "Politiques culturelles « ÉTÉ »"})
        texte = chemin.read_text(encoding="utf-8")
        assert "« ÉTÉ »" in texte, "les accents doivent rester lisibles à la main"
        assert "\n  " in texte, "le JSON doit être indenté"
        assert lire_json(chemin) == {"titre": "Politiques culturelles « ÉTÉ »"}


def test_lecture_fichier_absent_donne_defaut():
    with dossier_temporaire() as d:
        assert lire_json(Path(d) / "absent.json", defaut=[]) == []


def test_echec_d_ecriture_laisse_l_ancien_fichier_intact():
    with dossier_temporaire() as d:
        chemin = Path(d) / "a.json"
        ecrire_json(chemin, {"v": 1})
        with mock.patch.object(stockage.os, "replace", side_effect=OSError("disque plein")):
            try:
                ecrire_json(chemin, {"v": 2})
            except OSError:
                pass
            else:
                raise AssertionError("l'erreur doit remonter")
        assert lire_json(chemin) == {"v": 1}
        assert os.listdir(d) == ["a.json"], "aucun fichier temporaire ne doit traîner"


def test_acces_refuse_passager_est_retente():
    with dossier_temporaire() as d:
        chemin = Path(d) / "a.json"
        vrai_replace = os.replace
        appels = []

        def replace_capricieux(a, b):
            appels.append(1)
            if len(appels) < 3:
                raise PermissionError("verrouillé par Drive")
            vrai_replace(a, b)

        with mock.patch.object(stockage.os, "replace", replace_capricieux), \
                mock.patch.object(stockage, "PAUSE_ENTRE_TENTATIVES", 0):
            ecrire_json(chemin, {"v": 1})
        assert lire_json(chemin) == {"v": 1}


def test_acces_refuse_persistant_mentionne_acces_controle():
    with dossier_temporaire() as d:
        chemin = Path(d) / "a.json"
        with mock.patch.object(stockage.os, "replace", side_effect=PermissionError()), \
                mock.patch.object(stockage, "PAUSE_ENTRE_TENTATIVES", 0):
            try:
                ecrire_json(chemin, {"v": 1})
            except ErreurStockage as e:
                assert "Accès contrôlé aux dossiers" in str(e)
            else:
                raise AssertionError("ErreurStockage attendue")


def test_json_abime_donne_un_message_utile():
    with dossier_temporaire() as d:
        chemin = Path(d) / "a.json"
        chemin.write_text('{"v": 1,,}', encoding="utf-8")
        try:
            lire_json(chemin)
        except ErreurStockage as e:
            assert "sauvegardes" in str(e) and "ligne 1" in str(e)
        else:
            raise AssertionError("ErreurStockage attendue")


def test_json_avec_bom_est_lu():
    # Un fichier réparé à la main dans le Bloc-notes peut commencer par un BOM.
    with dossier_temporaire() as d:
        chemin = Path(d) / "a.json"
        chemin.write_bytes("﻿".encode() + json.dumps({"v": 1}).encode())
        assert lire_json(chemin) == {"v": 1}


def test_nettoyage_ne_supprime_que_les_temporaires_anciens():
    with dossier_temporaire() as d:
        ancien = Path(d) / (stockage.PREFIXE_TEMPORAIRE + "vieux")
        recent = Path(d) / (stockage.PREFIXE_TEMPORAIRE + "recent")
        autre = Path(d) / "memoire.json"
        for p in (ancien, recent, autre):
            p.write_text("x")
        il_y_a_2h = time.time() - 7200
        os.utime(ancien, (il_y_a_2h, il_y_a_2h))
        assert nettoyer_temporaires(Path(d)) == [ancien]
        assert recent.exists() and autre.exists()


if __name__ == "__main__":
    lancer(globals())
