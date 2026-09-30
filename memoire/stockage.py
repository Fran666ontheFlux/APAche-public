"""Lecture et écriture des fichiers JSON du dossier de données.

Écriture atomique : on écrit un fichier temporaire à côté de la cible puis on
le renomme par-dessus. Google Drive ne voit donc jamais un fichier à moitié
écrit, et une coupure pendant l'écriture laisse l'ancienne version intacte.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

PREFIXE_TEMPORAIRE = ".ecriture-"

# Sous Windows, Drive ou l'antivirus ouvrent brièvement les fichiers qu'ils
# viennent de voir changer ; le renommage échoue alors avec « accès refusé ».
# Quelques nouvelles tentatives suffisent presque toujours.
TENTATIVES = 8
PAUSE_ENTRE_TENTATIVES = 0.25


class ErreurStockage(Exception):
    """Erreur de lecture/écriture, formulée pour l'utilisateur."""


MESSAGE_ACCES_REFUSE = (
    "Impossible d'enregistrer dans « {chemin} » : Windows refuse l'accès.\n"
    "Causes probables :\n"
    "  • la protection « Accès contrôlé aux dossiers » de Windows Defender bloque "
    "Python. Ouvre Sécurité Windows → Protection contre les virus et menaces → "
    "Gérer la protection contre les ransomwares, et autorise python.exe ;\n"
    "  • le fichier est ouvert dans un autre programme, ou Google Drive est en "
    "train de le synchroniser : réessaie dans quelques secondes.\n"
    "Tes modifications ne sont pas perdues tant que l'outil reste ouvert."
)


def serialiser(donnees) -> bytes:
    return (json.dumps(donnees, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def ecrire_json(chemin: Path, donnees) -> None:
    ecrire_octets(chemin, serialiser(donnees))


def ecrire_octets(chemin: Path, contenu: bytes) -> None:
    """Écriture atomique : aussi pour les fichiers joints, qu'une coupure ne doit pas laisser à moitié copiés."""
    chemin = Path(chemin)
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        descripteur, temporaire = tempfile.mkstemp(
            prefix=PREFIXE_TEMPORAIRE + chemin.name + "-", dir=chemin.parent
        )
    except PermissionError as e:
        raise ErreurStockage(MESSAGE_ACCES_REFUSE.format(chemin=chemin)) from e
    try:
        with os.fdopen(descripteur, "wb") as f:
            f.write(contenu)
            f.flush()
            os.fsync(f.fileno())
        _remplacer(Path(temporaire), chemin)
    except BaseException:
        Path(temporaire).unlink(missing_ok=True)
        raise


def _remplacer(source: Path, cible: Path) -> None:
    for tentative in range(TENTATIVES):
        try:
            os.replace(source, cible)
            return
        except PermissionError as e:
            if tentative == TENTATIVES - 1:
                raise ErreurStockage(MESSAGE_ACCES_REFUSE.format(chemin=cible)) from e
            time.sleep(PAUSE_ENTRE_TENTATIVES)


def lire_json(chemin: Path, defaut=None):
    chemin = Path(chemin)
    if not chemin.exists():
        return defaut
    try:
        with open(chemin, encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ErreurStockage(
            f"Le fichier « {chemin.name} » est abîmé (ligne {e.lineno}, colonne {e.colno}) "
            f"et ne peut pas être lu. Rien n'a été modifié. Tu peux restaurer une copie "
            f"depuis le dossier « sauvegardes », ou l'ouvrir dans un éditeur de texte "
            f"pour corriger l'endroit indiqué."
        ) from e
    except UnicodeDecodeError as e:  # fichier coupé au milieu d'un caractère (synchronisation interrompue)
        raise ErreurStockage(
            f"Le fichier « {chemin.name} » est abîmé (coupé en cours de synchronisation ?) et ne peut pas "
            f"être lu. Rien n'a été modifié. Attends la fin de la synchronisation de Google Drive, ou "
            f"restaure une copie depuis le dossier « sauvegardes »."
        ) from e
    except PermissionError as e:
        raise ErreurStockage(MESSAGE_ACCES_REFUSE.format(chemin=chemin)) from e


def nettoyer_temporaires(dossier: Path, age_minimum_s: float = 3600) -> list[Path]:
    """Supprime les fichiers temporaires laissés par une écriture interrompue.

    On ne touche qu'aux fichiers anciens : un fichier récent peut appartenir à
    une écriture en cours.
    """
    supprimes = []
    limite = time.time() - age_minimum_s
    for p in Path(dossier).rglob(PREFIXE_TEMPORAIRE + "*"):  # y compris fichiers/ (fichiers joints)
        try:
            if p.stat().st_mtime < limite:
                p.unlink()
                supprimes.append(p)
        except OSError:
            pass
    return supprimes
