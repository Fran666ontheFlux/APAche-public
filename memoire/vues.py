"""Ce que l'interface affiche, calculé côté serveur.

L'interface ne tient aucune copie des données : chaque action renvoie la vue
à jour, citations et références déjà mises en forme. Ainsi la règle APA vit à
un seul endroit (apa.py), testée, et pas une seconde fois en JavaScript.
"""

from __future__ import annotations

import re

from . import apa, mise_en_forme
from .depot import Memoire
from .modele import NATURES, STATUTS_SOURCE, TYPES_SOURCE, DonneesInvalides, Source

LIBELLES_STATUTS = {"a_lire": "À lire", "lu": "Lu", "fiche": "Fiché"}
LIBELLES_NATURES = {"citation": "Citation", "paraphrase": "Paraphrase", "idee_perso": "Idée perso"}

# Champs d'une source que l'interface peut écrire (les autres sont gérés par l'outil).
CHAMPS_SOURCE_MODIFIABLES = {"type", "auteurs", "annee", "titre", "champs", "statut", "citee_partie1", "premiere_page"}
CHAMPS_EXTRAIT_MODIFIABLES = {"texte", "page_debut", "page_fin", "nature", "auteur_origine", "mots_cles",
                              "integre", "note", "section_plan"}


def schema() -> dict:
    return {
        "types": [{"cle": t, "libelle": apa.LIBELLES_TYPES[t],
                   "champs": [{"cle": c.cle, "libelle": c.libelle, "obligatoire": c.obligatoire, "genre": c.genre}
                              for c in apa.CHAMPS[t]]}
                  for t in TYPES_SOURCE],
        "statuts": [{"cle": s, "libelle": LIBELLES_STATUTS[s]} for s in STATUTS_SOURCE],
        "natures": [{"cle": n, "libelle": LIBELLES_NATURES[n]} for n in NATURES],
    }


def filtrer(corps: dict, autorises: set[str]) -> dict:
    inconnus = set(corps) - autorises
    if inconnus:
        raise DonneesInvalides(f"Champ non modifiable : « {sorted(inconnus)[0]} ».")
    return corps


def _mise(mise: apa.Mise | None) -> dict | None:
    return {"html": mise.html, "texte": mise.texte} if mise else None


def _etiquette(source: Source, r, suffixe: str, homonymes: set[str] = frozenset()) -> str:
    return apa.etiquette(source, r, suffixe, source.id in homonymes)


def vue_sources(m: Memoire) -> dict:
    r = m.projet.reglages_apa
    lettres = apa.suffixes(list(m.sources.values()))
    hom = apa.homonymes(list(m.sources.values()))
    extraits_par_source: dict[str, list] = {}
    for e in m.extraits.values():
        extraits_par_source.setdefault(e.source_id, []).append(e)
    lignes = []
    for s in m.sources.values():
        extraits = extraits_par_source.get(s.id, [])
        reference = apa.reference(s, r, lettres.get(s.id, ""))
        lignes.append({
            "id": s.id, "type": s.type, "libelle_type": apa.LIBELLES_TYPES[s.type], "statut": s.statut,
            "etiquette": _etiquette(s, r, lettres.get(s.id, ""), hom), "titre": s.titre,
            "citee_partie1": s.citee_partie1, "nb_extraits": len(extraits), "a_fichier": bool(s.fichier_joint),
            "nb_integres": sum(e.integre for e in extraits),
            "a_completer": reference.manques if reference else [],
            "date_modif": s.date_modif,
        })
    lignes.sort(key=lambda x: apa._cle_tri(x["etiquette"]))
    return {"sources": lignes}


def _vue_extrait(e, s: Source, r, suffixe: str, homonymes: set[str] = frozenset()) -> dict:
    """L'extrait et ses citations prêtes à copier (aucune pour une idée personnelle)."""
    options = dict(page_debut=e.page_debut, page_fin=e.page_fin, suffixe=suffixe, auteur_origine=e.auteur_origine,
                   avec_initiales=s.id in homonymes)
    d = e.vers_dict()
    if e.nature != "idee_perso":
        d["citation"] = _mise(apa.citation(s, r, **options))
        d["narrative"] = _mise(apa.citation(s, r, narrative=True, **options))
    if e.nature == "citation":
        passage = apa.citation_litterale(mise_en_forme.brut(e.texte), s, r, **options)
        # Le texte brut pour un collage simple ; en HTML, le gras et l'italique du passage (Google Docs).
        balise = e.texte.strip().strip("«»\"“”").strip()
        d["avec_texte"] = {"texte": passage.texte,
                           "html": f"« {mise_en_forme.vers_html(balise)} » {apa.citation(s, r, **options).html}"}
    return d


def _sources_resumees(m: Memoire, lettres: dict[str, str], ids=None, hom: set[str] = frozenset()) -> dict:
    r = m.projet.reglages_apa
    sources = {}
    for s in m.sources.values():
        if ids is not None and s.id not in ids:
            continue
        reference = apa.reference(s, r, lettres.get(s.id, ""))
        sources[s.id] = {"id": s.id, "etiquette": _etiquette(s, r, lettres.get(s.id, ""), hom), "type": s.type,
                         "libelle_type": apa.LIBELLES_TYPES[s.type], "annee": s.annee.strip(),
                         "titre": s.titre, "citee_partie1": s.citee_partie1, "reference": _mise(reference)}
    return sources


def vue_extraits(m: Memoire) -> dict:
    """Tous les extraits, pour la grille : filtrés dans le navigateur, sans aller-retour."""
    r = m.projet.reglages_apa
    lettres = apa.suffixes(list(m.sources.values()))
    hom = apa.homonymes(list(m.sources.values()))
    extraits = [_vue_extrait(e, m.sources[e.source_id], r, lettres.get(e.source_id, ""), hom)
                for e in m.extraits.values() if e.source_id in m.sources]
    return {"extraits": extraits, "sources": _sources_resumees(m, lettres, hom=hom)}


# --- Plan ---------------------------------------------------------------

def _avec_sous_themes(m: Memoire, ids: list[str]) -> set[str]:
    tous = set(ids)
    for mot in m.mots_cles.values():
        if mot.parent_id in tous:
            tous.add(mot.id)
    return tous


def _extraits_de_section(m: Memoire, section) -> list:
    """Rangés à la main dans la section, ou portant un de ses mots-clés (un thème couvre ses sous-thèmes)."""
    mots = _avec_sous_themes(m, section.mots_cles)
    return [e for e in m.extraits.values() if e.source_id in m.sources
            and (e.section_plan == section.id or (mots and mots & set(e.mots_cles)))]


def vue_plan(m: Memoire) -> dict:
    numeros = m.numeros_du_plan()
    sections = []
    for s in m.plan:
        extraits = _extraits_de_section(m, s)
        sections.append({**s.vers_dict(), "numero": numeros[s.id], "nb_extraits": len(extraits),
                         "nb_a_integrer": sum(not e.integre for e in extraits)})
    return {"sections": sections}


def vue_section(m: Memoire, id_: str) -> dict:
    """Les extraits d'une partie du plan : ceux qui restent à intégrer d'abord, puis par source."""
    section = m._section(id_)
    r = m.projet.reglages_apa
    lettres = apa.suffixes(list(m.sources.values()))
    hom = apa.homonymes(list(m.sources.values()))
    etiquettes = {s.id: _etiquette(s, r, lettres.get(s.id, ""), hom) for s in m.sources.values()}
    ordre = {e.id: i for i, e in enumerate(m.extraits.values())}
    extraits = sorted(_extraits_de_section(m, section),
                      key=lambda e: (e.integre, apa._cle_tri(etiquettes[e.source_id]), ordre[e.id]))
    return {
        "section": {**section.vers_dict(), "numero": m.numeros_du_plan()[section.id]},
        "extraits": [{**_vue_extrait(e, m.sources[e.source_id], r, lettres.get(e.source_id, ""), hom),
                      "a_la_main": e.section_plan == section.id} for e in extraits],
        "sources": _sources_resumees(m, lettres, {e.source_id for e in extraits}, hom),
    }


def vue_source(m: Memoire, id_: str) -> dict:
    s = m._source(id_)
    r = m.projet.reglages_apa
    suffixe = apa.suffixes(list(m.sources.values())).get(s.id, "")
    hom = apa.homonymes(list(m.sources.values()))
    extraits = [_vue_extrait(e, s, r, suffixe, hom) for e in m.extraits_de(s.id)]
    reference = apa.reference(s, r, suffixe)
    chemin = m.chemin_fichier(s)
    return {
        "source": s.vers_dict(),
        # Nom affiché sans l'identifiant ajouté à la copie (« article-3f2a….pdf » → « article.pdf »).
        "fichier": {"nom": re.sub(rf"-{s.id}(?=\.\w+$)", "", chemin.name), "present": chemin.exists()} if chemin else None,
        "etiquette": _etiquette(s, r, suffixe, hom),
        "reference": _mise(reference),
        "a_completer": reference.manques if reference else [],
        "extraits": extraits,
    }


def apercu_reference(m: Memoire, corps: dict) -> dict:
    """Référence d'une source en cours de saisie, sans rien enregistrer."""
    donnees = filtrer({k: v for k, v in corps.items() if k != "id"}, CHAMPS_SOURCE_MODIFIABLES)
    s = Source(**{"type": "article_revue", **donnees})
    s.valider()
    if corps.get("id"):
        s.id = corps["id"]  # même identifiant : garde sa lettre a/b parmi les autres sources
    autres = [x for x in m.sources.values() if x.id != s.id] + [s]
    reference = apa.reference(s, m.projet.reglages_apa, apa.suffixes(autres).get(s.id, ""))
    return {"reference": _mise(reference), "a_completer": reference.manques if reference else []}


def _raison(source: Source, integres: int) -> str:
    morceaux = []
    if source.citee_partie1:
        morceaux.append("déjà citée")
    if integres:
        morceaux.append(f"{integres} extrait{'s' if integres > 1 else ''} intégré{'s' if integres > 1 else ''}")
    return " · ".join(morceaux)


def vue_bibliographie(m: Memoire) -> dict:
    """La bibliographie finale : seulement les sources réellement
    citées (un extrait intégré, ou citée en partie 1), jamais les communications
    personnelles. Les auteurs cités de seconde main n'y sont pas : ce ne sont pas des sources."""
    r = m.projet.reglages_apa
    integres: dict[str, int] = {}
    for e in m.extraits.values():
        if e.integre:
            integres[e.source_id] = integres.get(e.source_id, 0) + 1
    citees, exclues = [], []
    for s in m.sources.values():
        if s.type == "communication_personnelle":
            continue
        (citees if s.citee_partie1 or integres.get(s.id) else exclues).append(s)
    lettres = apa.suffixes(list(m.sources.values()))
    hom = apa.homonymes(list(m.sources.values()))

    sections, html, texte = [], [], []
    for titre, membres in apa.bibliographie(citees, r, lettres, m.projet.bibliographie):
        references = [{"id": s.id, "etiquette": _etiquette(s, r, lettres.get(s.id, ""), hom), "html": mise.html,
                       "texte": mise.texte, "manques": mise.manques, "raison": _raison(s, integres.get(s.id, 0))}
                      for s, mise in membres]
        # Pour Google Docs : titres de partie en gras, italique des titres ; ni police ni taille,
        # pour que le texte collé prenne le style du paragraphe.
        bloc_html = f"<p><strong>{titre}</strong></p>" + "".join(f"<p>{x['html']}</p>" for x in references)
        bloc_texte = titre + "\n\n" + "\n".join(x["texte"] for x in references)
        sections.append({"titre": titre, "references": references, "copie": {"html": bloc_html, "texte": bloc_texte}})
        html.append(bloc_html)
        texte.append(bloc_texte)
    exclues.sort(key=lambda s: apa._cle_tri(_etiquette(s, r, lettres.get(s.id, ""), hom)))
    return {
        "sections": sections,
        "decoupage": m.projet.bibliographie,
        "copie": {"html": "".join(html), "texte": "\n\n".join(texte)},
        "a_completer": sum(bool(x["manques"]) for s in sections for x in s["references"]),
        "non_incluses": [{"id": s.id, "etiquette": _etiquette(s, r, lettres.get(s.id, ""), hom),
                          "nb_extraits": len(m.extraits_de(s.id))} for s in exclues],
    }
