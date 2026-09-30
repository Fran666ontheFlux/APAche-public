"""Verrou multi-PC (§ 10).

Ce n'est pas un vrai verrou : Drive synchronise avec du retard, donc deux PC
peuvent en théorie écrire chacun le leur. Il sert à prévenir l'utilisateur
dans le cas courant (portable resté ouvert à la maison), pas à garantir
l'exclusion.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime
from pathlib import Path

from .stockage import ecrire_json, lire_json

NOM_FICHIER = "verrou.json"


class MemoireDejaOuvert(Exception):
    def __init__(self, pc: str, depuis: datetime | None):
        self.pc = pc
        self.depuis = depuis
        super().__init__(message_verrou(pc, depuis))


def nom_pc() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname()


def _format_moment(depuis: datetime | None, aujourd_hui: datetime) -> str:
    if depuis is None:
        return ""
    heure = f"{depuis.hour} h {depuis.minute:02d}"
    if depuis.date() == aujourd_hui.date():
        return f" depuis {heure}"
    return f" depuis le {depuis:%d/%m} à {heure}"


def message_verrou(pc: str, depuis: datetime | None, aujourd_hui: datetime | None = None) -> str:
    moment = _format_moment(depuis, aujourd_hui or datetime.now())
    return (
        f"Le mémoire semble ouvert sur {pc}{moment}. Ferme-le là-bas, "
        f"ou attends la fin de la synchronisation (Google Drive, OneDrive…)."
    )


def lire(dossier: Path) -> dict | None:
    return lire_json(Path(dossier) / NOM_FICHIER)


def prendre(dossier: Path, forcer: bool = False) -> None:
    """Pose le verrou, ou lève MemoireDejaOuvert s'il appartient à un autre PC.

    Un verrou laissé par ce même PC vient d'une fermeture brutale (le serveur
    refuse de démarrer deux fois sur le même port) : on le reprend sans rien dire.
    """
    existant = lire(dossier)
    if existant and not forcer and existant.get("pc") != nom_pc():
        try:
            depuis = datetime.fromisoformat(existant.get("depuis", ""))
        except ValueError:
            depuis = None
        raise MemoireDejaOuvert(existant.get("pc") or "un autre PC", depuis)
    ecrire_json(
        Path(dossier) / NOM_FICHIER,
        {"pc": nom_pc(), "depuis": datetime.now().isoformat(timespec="seconds")},
    )


def rendre(dossier: Path) -> None:
    # On ne supprime que notre propre verrou : si l'autre PC l'a repris entre-temps
    # (« ouvrir quand même »), le sien doit rester.
    existant = lire(dossier)
    if existant and existant.get("pc") == nom_pc():
        (Path(dossier) / NOM_FICHIER).unlink(missing_ok=True)
