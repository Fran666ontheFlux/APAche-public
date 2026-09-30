"""Sauvegardes datées et détection des conflits Google Drive (§ 10)."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from .stockage import PREFIXE_TEMPORAIRE

NOM_DOSSIER = "sauvegardes"
A_GARDER = 30
_MOTIF = re.compile(r"^memoire_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.json$")


def lister(dossier: Path) -> list[Path]:
    """Sauvegardes existantes, de la plus ancienne à la plus récente."""
    rep = Path(dossier) / NOM_DOSSIER
    if not rep.is_dir():
        return []
    # Le nom encode la date au format ISO : l'ordre alphabétique est chronologique.
    return sorted(p for p in rep.iterdir() if _MOTIF.match(p.name))


def sauvegarder(fichier_donnees: Path, moment: datetime | None = None) -> Path | None:
    fichier_donnees = Path(fichier_donnees)
    if not fichier_donnees.exists():
        return None
    moment = moment or datetime.now()
    rep = fichier_donnees.parent / NOM_DOSSIER
    rep.mkdir(exist_ok=True)
    cible = rep / f"memoire_{moment:%Y-%m-%d_%H-%M-%S}.json"
    shutil.copy2(fichier_donnees, cible)
    purger(fichier_donnees.parent)
    return cible


def sauvegarde_du_jour_faite(dossier: Path, jour: datetime | None = None) -> bool:
    date = f"{(jour or datetime.now()):%Y-%m-%d}"
    return any(_MOTIF.match(p.name).group(1) == date for p in lister(dossier))


def sauvegarde_quotidienne(fichier_donnees: Path, moment: datetime | None = None) -> Path | None:
    if sauvegarde_du_jour_faite(Path(fichier_donnees).parent, moment):
        return None
    return sauvegarder(fichier_donnees, moment)


def purger(dossier: Path, a_garder: int = A_GARDER) -> list[Path]:
    anciennes = lister(dossier)[:-a_garder] if a_garder else lister(dossier)
    for p in anciennes:
        p.unlink(missing_ok=True)
    return anciennes


def detecter_conflits(dossier: Path, noms_attendus: tuple[str, ...]) -> list[Path]:
    """Copies créées par Drive quand deux PC ont modifié le même fichier.

    Drive garde les deux versions sous des noms voisins (« memoire (1).json »,
    ou un nom contenant « conflict »). Le motif est volontairement large :
    mieux vaut signaler un fichier de trop que manquer un vrai conflit.
    """
    racines = {Path(n).stem.lower() for n in noms_attendus}
    trouves = []
    for p in Path(dossier).iterdir():
        if not p.is_file() or p.name in noms_attendus or p.name.startswith(PREFIXE_TEMPORAIRE):
            continue
        nom = p.name.lower()
        if "conflict" in nom or "conflit" in nom or any(nom.startswith(r) for r in racines):
            trouves.append(p)
    return sorted(trouves)
