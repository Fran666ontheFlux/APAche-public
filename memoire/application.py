"""État de l'application entre deux requêtes : quel mémoire est ouvert, où.

Le chemin du dossier de données est propre à chaque PC (lettre de lecteur
Drive différente, nom d'utilisateur différent) : il vit dans un petit fichier
local, ignoré par git, et jamais dans le dossier Drive lui-même.
"""

from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path

from . import stockage
from .depot import Memoire
from .verrou import MemoireDejaOuvert


def _fichier_reglages_locaux() -> Path:
    """Depuis le code : à côté de lui (ignoré par git). Depuis APAche.exe, dont le dossier
    peut être en lecture seule ou remplacé à chaque mise à jour : dans le profil Windows."""
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("APPDATA") or Path.home()) / "APAche" / "reglages_locaux.json"
    return Path(__file__).resolve().parents[1] / "reglages_locaux.json"


FICHIER_REGLAGES_LOCAUX = _fichier_reglages_locaux()


class Application:
    def __init__(self, fichier_reglages: Path = FICHIER_REGLAGES_LOCAUX):
        self.fichier_reglages = Path(fichier_reglages)
        self.memoire: Memoire | None = None
        self.probleme: dict | None = None
        # Le serveur traite les requêtes en parallèle : un seul accès aux
        # données à la fois, sinon deux écritures pourraient s'entrecroiser.
        self.acces = threading.RLock()

    def dossier_configure(self) -> str | None:
        return (stockage.lire_json(self.fichier_reglages, {}) or {}).get("dossier_donnees")

    def _memoriser_dossier(self, dossier: str) -> None:
        reglages = stockage.lire_json(self.fichier_reglages, {}) or {}
        reglages["dossier_donnees"] = dossier
        stockage.ecrire_json(self.fichier_reglages, reglages)

    def etat(self) -> dict:
        with self.acces:
            return {
                "ouvert": self.memoire is not None,
                "dossier": str(self.memoire.dossier) if self.memoire else self.dossier_configure(),
                "conflits": [p.name for p in self.memoire.conflits] if self.memoire else [],
                "probleme": self.probleme,
            }

    def ouvrir(self, dossier: str | None = None, forcer: bool = False, creer: bool = False) -> dict:
        with self.acces:
            # Les guillemets viennent de « Copier en tant que chemin » de l'Explorateur.
            dossier = (dossier or self.dossier_configure() or "").strip().strip('"')
            if not dossier:
                self.probleme = None
                return self.etat()
            if self.memoire and Path(dossier) != self.memoire.dossier:
                self.fermer()
            chemin = Path(dossier)
            if self.memoire is None and not chemin.is_dir():
                parent_existe = chemin.parent.is_dir() and chemin.parent != chemin
                if creer and parent_existe:
                    chemin.mkdir()
                else:
                    self.probleme = {
                        "type": "absent", "dossier": dossier, "creable": parent_existe,
                        "message": (f"Le dossier « {chemin.name} » n'existe pas encore dans "
                                    f"« {chemin.parent} ». Le créer ?") if parent_existe else
                                   (f"Le dossier « {dossier} » est introuvable. Vérifie le chemin, "
                                    f"et que ton dossier synchronisé (Google Drive, OneDrive…) est disponible."),
                    }
                    return self.etat()
            if self.memoire is None:
                try:
                    self.memoire = Memoire.ouvrir(Path(dossier), forcer=forcer)
                    self.probleme = None
                except MemoireDejaOuvert as e:
                    self.probleme = {"type": "verrou", "message": str(e), "dossier": dossier}
                except stockage.ErreurStockage as e:
                    self.probleme = {"type": "stockage", "message": str(e), "dossier": dossier}
                except Exception as e:  # jamais un lanceur qui plante : l'écran d'accueil explique
                    traceback.print_exc()
                    self.probleme = {"type": "stockage", "dossier": dossier, "message": (
                        f"Le mémoire n'a pas pu être ouvert ({type(e).__name__}). Rien n'a été modifié. "
                        f"Le détail est dans la fenêtre noire ; tu peux restaurer une copie depuis « sauvegardes »."
                    )}
                if self.memoire:
                    self._memoriser_dossier(dossier)
            return self.etat()

    def fermer(self) -> None:
        with self.acces:
            if self.memoire:
                self.memoire.fermer()
                self.memoire = None
