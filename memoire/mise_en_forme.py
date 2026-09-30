"""Gras et italique dans le texte d'un extrait.

Le texte reste du texte simple : seules quatre balises y ont un sens, <b> </b> <i> </i>.
Tout le reste est du texte (« a < b » reste « a < b »), si bien que les extraits
d'avant cette mise en forme restent valables tels quels. La recherche, les
suggestions de mots-clés et la copie en texte brut travaillent sur `brut()`.
"""

from __future__ import annotations

import html
import re

BALISE = re.compile(r"<(/?)([bi])>")


def segments(texte: str) -> list[tuple[str, bool, bool]]:
    """[(morceau, gras, italique)], dans l'ordre ; une balise fermante orpheline est ignorée."""
    ouverts = {"b": 0, "i": 0}
    morceaux: list[tuple[str, bool, bool]] = []
    position = 0
    for m in BALISE.finditer(texte or ""):
        if m.start() > position:
            morceaux.append((texte[position:m.start()], ouverts["b"] > 0, ouverts["i"] > 0))
        cle = m.group(2)
        ouverts[cle] = max(0, ouverts[cle] + (-1 if m.group(1) else 1))
        position = m.end()
    if position < len(texte or ""):
        morceaux.append((texte[position:], ouverts["b"] > 0, ouverts["i"] > 0))
    return morceaux


def brut(texte: str) -> str:
    return BALISE.sub("", texte or "")


def nettoyer(texte: str) -> str:
    """Forme canonique : balises équilibrées, pas de balise vide, morceaux voisins de même style réunis."""
    fusion: list[list] = []
    for morceau, gras, italique in segments(texte):
        if fusion and fusion[-1][1:] == [gras, italique]:
            fusion[-1][0] += morceau
        else:
            fusion.append([morceau, gras, italique])
    sortie = []
    for morceau, gras, italique in fusion:
        if not morceau:
            continue
        if morceau.strip() == "":  # une espace en gras ne se voit pas : pas de balise pour elle
            gras = italique = False
        ouvre = ("<b>" if gras else "") + ("<i>" if italique else "")
        ferme = ("</i>" if italique else "") + ("</b>" if gras else "")
        sortie.append(ouvre + morceau + ferme)
    return re.sub(r"</([bi])><\1>", "", "".join(sortie))


def vers_html(texte: str) -> str:
    """Pour le presse-papiers (Google Docs) : le texte échappé, gras et italique en vraies balises."""
    sortie = []
    for morceau, gras, italique in segments(texte):
        t = html.escape(morceau, quote=False)
        if italique:
            t = f"<i>{t}</i>"
        if gras:
            t = f"<b>{t}</b>"
        sortie.append(t)
    return "".join(sortie)
