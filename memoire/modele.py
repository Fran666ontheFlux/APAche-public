"""Modèle de données.

L'unité de travail est l'extrait : la source ne porte que la bibliographie.
Chaque objet se convertit en dict JSON et inversement ; les clés inconnues
sont conservées dans `autres` pour qu'une version plus récente de l'outil,
ouverte sur l'autre PC, ne perde pas de données en passant par une plus ancienne.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime

VERSION_SCHEMA = 1

DECOUPAGES_BIBLIOGRAPHIE = ("une_liste", "trois_parties")

TYPES_SOURCE = (
    "livre",
    "chapitre",
    "article_revue",
    "article_presse",
    "rapport",
    "texte_legal",
    "page_web",
    "memoire_these",
    "document_institutionnel",  # catalogue, dossier de presse, rapport annuel
    "audiovisuel",              # vidéo, podcast, conférence
    "communication_colloque",   # communication non publiée dans des actes
    "support_cours",            # syllabus, notes de cours publiées
    "jurisprudence",            # arrêt, jugement
    "communication_personnelle",
)
STATUTS_SOURCE = ("a_lire", "lu", "fiche")
PROVENANCES = ("saisie", "import_bibliographie", "import_extraits", "depot_fichier")
NATURES = ("citation", "paraphrase", "idee_perso")


class DonneesInvalides(ValueError):
    """Erreur de contenu, formulée pour l'utilisateur."""


def nouvel_id() -> str:
    # Identifiant aléatoire plutôt qu'un compteur : deux PC qui créent un objet
    # chacun de leur côté ne peuvent pas produire le même identifiant.
    return uuid.uuid4().hex[:12]


def maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _verifier_personnes(personnes, quoi: str) -> None:
    # Les données arrivent aussi de l'interface : une forme inattendue
    # casserait la mise en forme APA à la prochaine lecture.
    if not isinstance(personnes, list) or not all(
            isinstance(p, dict) and set(p) <= {"nom", "prenom", "organisation"}
            and all(isinstance(v, str) for v in p.values()) for p in personnes):
        raise DonneesInvalides(f"{quoi} : liste de personnes illisible.")


def _verifier_textes(objet, *noms: str) -> None:
    for nom in noms:
        if not isinstance(getattr(objet, nom), str):
            raise DonneesInvalides(f"Champ « {nom} » : du texte est attendu.")


def _depuis_dict(cls, d: dict):
    connus = {f.name for f in fields(cls)} - {"autres"}
    valeurs = {k: v for k, v in d.items() if k in connus}
    objet = cls(**valeurs)
    objet.autres = {k: v for k, v in d.items() if k not in connus}
    return objet


def _vers_dict(objet) -> dict:
    d = {f.name: getattr(objet, f.name) for f in fields(objet) if f.name != "autres"}
    d.update(objet.autres)
    return d


@dataclass
class ReglagesAPA:
    # Valeurs par défaut du français (guide APA des Bibliothèques ULB, 2024).
    # Le guide ULB écrit « in » pour une source secondaire ; « cité dans » est
    # l'usage APA en français, gardé par défaut et réglable.
    conjonction: str = "et"
    sans_date: str = "s. d."
    cite_dans: str = "cité dans"
    page: str = "p."
    pages: str = "p."  # le guide ULB écrit « p. 525-528 », pas « pp. »
    directeur: str = "(dir.)"
    directeurs: str = "(dir.)"
    consulte_le: str = "consulté le"
    autres: dict = field(default_factory=dict)

    @classmethod
    def depuis_dict(cls, d: dict) -> ReglagesAPA:
        return _depuis_dict(cls, d)

    def vers_dict(self) -> dict:
        return _vers_dict(self)


@dataclass
class Projet:
    titre: str = ""
    sous_titre: str = ""
    auteur: str = ""
    promoteur: str = ""
    annee_academique: str = ""
    # Chercher une référence par DOI ou ISBN sur internet. Désactivé par
    # défaut : l'outil reste entièrement hors ligne tant que l'utilisateur ne l'autorise pas.
    recherche_en_ligne: bool = False
    # « une_liste » : la liste unique de l'APA ; « trois_parties » : références scientifiques,
    # sources non scientifiques, sitographie (Guide du Master de l'ULB, par exemple).
    bibliographie: str = "une_liste"
    reglages_apa: ReglagesAPA = field(default_factory=ReglagesAPA)
    autres: dict = field(default_factory=dict)

    @classmethod
    def depuis_dict(cls, d: dict) -> Projet:
        d = dict(d)
        reglages = ReglagesAPA.depuis_dict(d.pop("reglages_apa", {}))
        projet = _depuis_dict(cls, d)
        projet.reglages_apa = reglages
        return projet

    def vers_dict(self) -> dict:
        d = _vers_dict(self)
        d["reglages_apa"] = self.reglages_apa.vers_dict()
        return d


@dataclass
class MotCle:
    libelle: str
    id: str = field(default_factory=nouvel_id)
    parent_id: str | None = None
    synonymes: list[str] = field(default_factory=list)
    couleur: str = ""
    origine_import: dict | None = None  # voir import_extraits : rejouer l'import sans doublon
    autres: dict = field(default_factory=dict)

    @classmethod
    def depuis_dict(cls, d: dict) -> MotCle:
        return _depuis_dict(cls, d)

    def vers_dict(self) -> dict:
        return _vers_dict(self)


@dataclass
class Source:
    """Auteurs : liste de {"nom", "prenom"} ou {"organisation"}.

    Auteurs, année et titre sont communs à tous les types et servent aux
    filtres ; les autres champs bibliographiques dépendent du type et vivent
    dans `champs`.
    """

    type: str
    id: str = field(default_factory=nouvel_id)
    auteurs: list[dict] = field(default_factory=list)
    annee: str = ""
    titre: str = ""
    champs: dict = field(default_factory=dict)
    statut: str = "a_lire"
    citee_partie1: bool = False
    fichier_joint: str | None = None  # chemin relatif au dossier de données (fichiers/…)
    premiere_page: str = ""  # page imprimée de la 1re page du PDF, si l'utilisateur l'a corrigée
    provenance: str = "saisie"
    origine_import: dict | None = None
    date_ajout: str = field(default_factory=maintenant)
    date_modif: str = field(default_factory=maintenant)
    autres: dict = field(default_factory=dict)

    def valider(self) -> None:
        if self.type not in TYPES_SOURCE:
            raise DonneesInvalides(f"Type de source inconnu : « {self.type} ».")
        if self.statut not in STATUTS_SOURCE:
            raise DonneesInvalides(f"Statut de source inconnu : « {self.statut} ».")
        if self.provenance not in PROVENANCES:
            raise DonneesInvalides(f"Provenance inconnue : « {self.provenance} ».")
        _verifier_textes(self, "annee", "titre", "premiere_page")
        _verifier_personnes(self.auteurs, "Auteurs")
        if not isinstance(self.champs, dict):
            raise DonneesInvalides("Champs bibliographiques illisibles.")
        if "directeurs" in self.champs:
            _verifier_personnes(self.champs["directeurs"], "Directeurs")
        if not isinstance(self.citee_partie1, bool):
            raise DonneesInvalides("« Cité en partie 1 » doit être oui ou non.")

    @classmethod
    def depuis_dict(cls, d: dict) -> Source:
        return _depuis_dict(cls, d)

    def vers_dict(self) -> dict:
        return _vers_dict(self)


@dataclass
class Extrait:
    source_id: str
    texte: str = ""
    id: str = field(default_factory=nouvel_id)
    page_debut: str = ""  # texte : les pages peuvent être « xii » ou « 12a »
    page_fin: str = ""
    nature: str = "citation"
    auteur_origine: dict | None = None  # {"auteurs": [...], "annee": "..."} — § 7.3
    mots_cles: list[str] = field(default_factory=list)
    integre: bool = False
    section_plan: str | None = None
    note: str = ""
    origine_import: dict | None = None
    date_ajout: str = field(default_factory=maintenant)
    date_modif: str = field(default_factory=maintenant)
    autres: dict = field(default_factory=dict)

    def valider(self) -> None:
        _verifier_textes(self, "texte", "page_debut", "page_fin", "note")
        if not isinstance(self.integre, bool):
            raise DonneesInvalides("« Intégré » doit être oui ou non.")
        if self.section_plan is not None and not isinstance(self.section_plan, str):
            raise DonneesInvalides("Partie du plan illisible.")
        if not isinstance(self.mots_cles, list) or not all(isinstance(m, str) for m in self.mots_cles):
            raise DonneesInvalides("Liste de mots-clés illisible.")
        if self.auteur_origine is not None:
            if not isinstance(self.auteur_origine, dict):
                raise DonneesInvalides("Auteur d'origine illisible.")
            _verifier_personnes(self.auteur_origine.get("auteurs", []), "Auteur d'origine")
        if self.nature not in NATURES:
            raise DonneesInvalides(f"Nature d'extrait inconnue : « {self.nature} ».")
        if self.nature == "citation" and not str(self.page_debut).strip():
            raise DonneesInvalides(
                "Une citation littérale doit avoir un numéro de page. "
                "Indique la page, ou classe l'extrait en paraphrase."
            )

    @classmethod
    def depuis_dict(cls, d: dict) -> Extrait:
        return _depuis_dict(cls, d)

    def vers_dict(self) -> dict:
        return _vers_dict(self)


@dataclass
class Section:
    """Une partie du plan du mémoire. Niveau 1 : chapitre ; 2 : section.
    Le numéro (1, 1.1, 1.2, 2…) se déduit de l'ordre : il n'est pas stocké, pour
    ne jamais être faux après un déplacement."""

    titre: str
    id: str = field(default_factory=nouvel_id)
    niveau: int = 1
    mots_cles: list[str] = field(default_factory=list)
    autres: dict = field(default_factory=dict)

    def valider(self) -> None:
        if not isinstance(self.titre, str) or not self.titre.strip():
            raise DonneesInvalides("Une partie du plan doit avoir un titre.")
        if self.niveau not in (1, 2):
            raise DonneesInvalides("Une partie du plan est un chapitre ou une section.")
        if not isinstance(self.mots_cles, list) or not all(isinstance(m, str) for m in self.mots_cles):
            raise DonneesInvalides("Liste de mots-clés illisible.")

    @classmethod
    def depuis_dict(cls, d: dict) -> Section:
        return _depuis_dict(cls, d)

    def vers_dict(self) -> dict:
        return _vers_dict(self)
