"""Recherche dans le texte des fichiers joints.

Le texte de chaque PDF ou Word est lu une fois puis gardé dans « index/ » du
dossier de données (voir fichiers._lire) : la première recherche lit les fichiers
pas encore lus, par tranches, pour que l'interface puisse montrer où elle en est ;
les suivantes sont immédiates.

Tous les mots cherchés doivent être sur la même page ; accents et majuscules
ne comptent pas. Chaque résultat donne la page imprimée et le passage.
"""

from __future__ import annotations

import time
import unicodedata

from . import apa, fichiers
from .depot import Memoire
from .modele import DonneesInvalides

DOSSIER_INDEX = "index"
LIMITE = 200            # résultats au plus : au-delà, mieux vaut préciser la recherche
AUTOUR = 110            # caractères de contexte de part et d'autre du passage trouvé
BUDGET_LECTURE = 3.0    # secondes de lecture par appel : l'interface affiche la progression entre deux


def _plier(texte: str) -> str:
    """Minuscules sans accents, caractère pour caractère : les positions restent celles du texte d'origine."""
    return "".join((unicodedata.normalize("NFD", c)[0] if c.isalpha() else c).lower()[:1] or c for c in texte)


def _fichiers(memoire: Memoire):
    for s in memoire.sources.values():
        chemin = memoire.chemin_fichier(s)
        if chemin and chemin.exists():
            yield s, chemin


# Fichiers qu'aucun lecteur n'a pu lire, pour la séance : ne pas les relire à chaque recherche.
# La clé change si le fichier est remplacé : il sera alors retenté.
_illisibles: set[tuple[str, int, int]] = set()


def _cle(chemin) -> tuple[str, int, int]:
    etat = chemin.stat()
    return str(chemin), etat.st_mtime_ns, etat.st_size


def indexer(memoire: Memoire) -> dict:
    """Lit les fichiers pas encore lus, dans la limite du budget de temps. Renvoie ce qu'il reste."""
    dossier = memoire.dossier / DOSSIER_INDEX
    debut = time.monotonic()
    total = restants = 0
    illisibles = []
    for s, chemin in _fichiers(memoire):
        total += 1
        if fichiers.deja_lu(chemin, dossier):
            continue
        if _cle(chemin) in _illisibles:
            illisibles.append(s.id)
            continue
        if time.monotonic() - debut > BUDGET_LECTURE:
            restants += 1
            continue
        try:
            fichiers.texte_du_fichier(chemin, s.premiere_page, dossier)
        except DonneesInvalides:
            _illisibles.add(_cle(chemin))
            illisibles.append(s.id)  # protégé ou abîmé : on ne le cherchera pas, sans bloquer les autres
    return {"total": total, "restants": restants, "illisibles": illisibles}


def rechercher(memoire: Memoire, requete: str) -> dict:
    mots = [m for m in _plier(requete).split() if len(m) >= 2]
    if not mots:
        raise DonneesInvalides("Écris au moins un mot de deux lettres.")
    dossier = memoire.dossier / DOSSIER_INDEX
    r = memoire.projet.reglages_apa
    lettres = apa.suffixes(list(memoire.sources.values()))
    hom = apa.homonymes(list(memoire.sources.values()))
    resultats, non_lus, trop = [], 0, False
    for s, chemin in _fichiers(memoire):
        if not fichiers.deja_lu(chemin, dossier):
            non_lus += 1
            continue
        try:
            lu = fichiers.texte_du_fichier(chemin, s.premiere_page, dossier)
        except DonneesInvalides:
            continue
        for page in lu["pages"]:
            plie = _plier(page["texte"])
            if not all(m in plie for m in mots):
                continue
            if len(resultats) >= LIMITE:
                trop = True
                break
            position = min(plie.find(m) for m in mots)
            debut, fin = max(0, position - AUTOUR), min(len(page["texte"]), position + AUTOUR)
            passage = page["texte"][debut:fin]
            plie_passage = plie[debut:fin]
            surlignes = sorted({(i, i + len(m)) for m in mots for i in _positions(plie_passage, m)})
            resultats.append({
                "source_id": s.id, "etiquette": apa.etiquette(s, r, lettres.get(s.id, ""), s.id in hom),
                "page": page["etiquette"], "passage": passage, "surlignes": surlignes,
                "coupe_debut": debut > 0, "coupe_fin": fin < len(page["texte"]),
            })
    return {"resultats": resultats, "non_lus": non_lus, "trop": trop}


def _positions(texte: str, mot: str) -> list[int]:
    positions, i = [], texte.find(mot)
    while i != -1:
        positions.append(i)
        i = texte.find(mot, i + 1)
    return positions
