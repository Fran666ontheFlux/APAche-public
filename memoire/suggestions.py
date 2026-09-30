"""Suggestion de mots-clés d'après le texte d'un extrait.

On cherche les mots-clés et leurs synonymes dans le texte, après normalisation :
minuscules, sans accents, pluriels et féminins courants ramenés à une racine
(racinisation simple, faite à la main : pas de dépendance pour si peu).

L'outil propose, l'utilisateur décide : rien n'est jamais classé en silence.
`mesurer` dit honnêtement ce que valent ces propositions sur les extraits déjà
classés à la main, pour ne pas livrer une fonction qui induit en erreur.
"""

from __future__ import annotations

import re
import unicodedata

from . import mise_en_forme
from .depot import Memoire
from .modele import MotCle

MOTS_VIDES = {"le", "la", "les", "l", "de", "des", "du", "d", "et", "ou", "en", "un", "une", "a", "au", "aux",
              "the", "of", "and", "in", "on", "to", "for", "sur", "par", "pour"}
# Terminaisons féminines et plurielles courantes → forme de base (français, un peu d'anglais).
FINALES = (("eaux", "eau"), ("aux", "al"), ("ies", "y"), ("ienne", "ien"), ("elle", "el"), ("euse", "eur"),
           ("trice", "teur"), ("ive", "if"), ("ere", "er"))
LONGUEUR_PREFIXE = 5  # une racine d'au moins 5 lettres couvre ses dérivés : « cultur » → « culturel »

MOT = re.compile(r"[^\W\d_]+")


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if not unicodedata.combining(c)).casefold()


def racine(mot: str) -> str:
    m = _sans_accents(mot)
    for fin, remplacement in FINALES:
        if m.endswith(fin) and len(m) > len(fin) + 2:
            return m[:-len(fin)] + remplacement
    if len(m) > 3 and m[-1] in "sx":
        m = m[:-1]
        for fin, remplacement in FINALES:
            if m.endswith(fin) and len(m) > len(fin) + 2:
                return m[:-len(fin)] + remplacement
    if len(m) > 4 and m.endswith("e"):
        m = m[:-1]
    return m


def jetons(texte: str) -> list[tuple[str, int, int]]:
    """(racine, début, fin) de chaque mot, positions dans le texte d'origine (pour le surlignage)."""
    return [(racine(m.group()), m.start(), m.end()) for m in MOT.finditer(texte)
            if _sans_accents(m.group()) not in MOTS_VIDES]


def termes(mot: MotCle) -> list[list[str]]:
    """Chaque libellé ou synonyme devient une liste de racines, mots vides ôtés."""
    resultat = []
    for expression in [mot.libelle, *mot.synonymes]:
        racines = [racine(m) for m in MOT.findall(expression) if _sans_accents(m) not in MOTS_VIDES]
        if racines:
            resultat.append(racines)
    return resultat


def _correspond(terme: str, mot: str) -> bool:
    return mot == terme or (len(terme) >= LONGUEUR_PREFIXE and mot.startswith(terme))


def suggerer(memoire: Memoire, texte: str) -> list[dict]:
    """Mots-clés dont un libellé ou synonyme apparaît dans le texte (tous ses mots, dans n'importe quel ordre)."""
    mots_du_texte = jetons(texte)
    suggestions = []
    for mot in memoire.mots_cles.values():
        passages, trouves = [], []
        for terme in termes(mot):
            positions = []
            for partie in terme:
                touches = [(d, f) for r, d, f in mots_du_texte if _correspond(partie, r)]
                if not touches:
                    positions = []
                    break
                positions.extend(touches)
            if positions:
                passages.extend(positions)
                trouves.append(" ".join(texte[d:f] for d, f in positions[:3]))
        if passages:
            suggestions.append({"id": mot.id, "libelle": mot.libelle, "termes": sorted(set(trouves)),
                                "passages": sorted(set(passages))})
    return sorted(suggestions, key=lambda s: s["passages"][0])


def _theme(memoire: Memoire, id_: str) -> str:
    """Un sous-thème compte pour son thème : c'est ainsi que la grille filtre."""
    mot = memoire.mots_cles.get(id_)
    while mot is not None and mot.parent_id in memoire.mots_cles:
        mot = memoire.mots_cles[mot.parent_id]
    return mot.id if mot else id_


def mesurer(memoire: Memoire) -> dict:
    """Sur les extraits déjà classés : part des propositions justes, part des mots-clés oubliés."""
    proposes = justes = poses = retrouves = extraits = 0
    for e in memoire.extraits.values():
        if not e.mots_cles:
            continue
        extraits += 1
        attendus = {_theme(memoire, m) for m in e.mots_cles}
        suggeres = {_theme(memoire, s["id"]) for s in suggerer(memoire, mise_en_forme.brut(e.texte))}
        proposes += len(suggeres)
        justes += len(suggeres & attendus)
        poses += len(attendus)
        retrouves += len(suggeres & attendus)
    return {
        "extraits": extraits,
        "justes": round(100 * justes / proposes) if proposes else None,       # précision
        "retrouves": round(100 * retrouves / poses) if poses else None,       # rappel
        "proposes": proposes,
    }
