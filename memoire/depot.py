"""Le mémoire ouvert : chargement, enregistrement et opérations sur les données.

Tout tient dans un seul fichier `memoire.json`. Un fichier unique se remplace
d'un bloc ; avec plusieurs fichiers, une synchronisation Drive interrompue
pourrait laisser des extraits pointant vers une source absente.

Chaque modification est enregistrée aussitôt : on ne perd rien si le navigateur
ou le PC se ferme sans prévenir.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import fichiers, mise_en_forme, sauvegardes, stockage, verrou
from .modele import DECOUPAGES_BIBLIOGRAPHIE, VERSION_SCHEMA, DonneesInvalides, Extrait, MotCle, Projet, Section, Source, maintenant

NOM_FICHIER = "memoire.json"
DOSSIER_FICHIERS = "fichiers"
NOMS_ATTENDUS = (NOM_FICHIER, verrou.NOM_FICHIER)


class ConfirmationRequise(Exception):
    """L'opération touche des données existantes : l'interface doit demander."""

    def __init__(self, message: str, nombre: int):
        self.nombre = nombre
        super().__init__(message)


def _pluriel(n: int, mot: str) -> str:
    return f"{n} {mot}{'s' if n > 1 else ''}"


class Memoire:
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.projet = Projet()
        self.mots_cles: dict[str, MotCle] = {}
        self.sources: dict[str, Source] = {}
        self.extraits: dict[str, Extrait] = {}
        self.plan: list[Section] = []  # dans l'ordre du mémoire
        self.autres: dict = {}
        self.conflits: list[Path] = []
        # Ce que ce PC a lu ou écrit en dernier dans memoire.json : (date, taille), empreinte.
        # Avant chaque écriture on vérifie que le fichier n'a pas changé entre-temps.
        self._vu: tuple[tuple[int, int] | None, str | None] = (None, None)

    @property
    def fichier(self) -> Path:
        return self.dossier / NOM_FICHIER

    # --- Ouverture et fermeture ---------------------------------------------

    @classmethod
    def ouvrir(cls, dossier: Path, forcer: bool = False) -> Memoire:
        dossier = Path(dossier)
        if not dossier.is_dir():
            raise stockage.ErreurStockage(
                f"Le dossier de données « {dossier} » n'existe pas. Vérifie le chemin "
                f"dans les réglages, et que ton dossier synchronisé (Google Drive, OneDrive…) est disponible."
            )
        # Charger avant de prendre le verrou : si le fichier est abîmé, on
        # s'arrête sans laisser de verrou derrière soi.
        memoire = cls(dossier)
        memoire._charger()
        verrou.prendre(dossier, forcer=forcer)
        try:
            stockage.nettoyer_temporaires(dossier)
            sauvegardes.sauvegarde_quotidienne(memoire.fichier)
            memoire.conflits = sauvegardes.detecter_conflits(dossier, NOMS_ATTENDUS)
        except OSError as e:  # sauvegarde impossible (disque plein, Drive…) : ne pas garder le verrou
            verrou.rendre(dossier)
            raise stockage.ErreurStockage(
                f"Impossible de faire la sauvegarde du jour dans « {dossier / sauvegardes.NOM_DOSSIER} » ({e}). "
                f"Vérifie la place sur le disque et que le dossier est disponible, puis réessaie."
            ) from e
        return memoire

    def fermer(self) -> None:
        sauvegardes.sauvegarder(self.fichier)
        verrou.rendre(self.dossier)

    def _signature(self) -> tuple[int, int] | None:
        try:
            etat = self.fichier.stat()
        except FileNotFoundError:
            return None
        return etat.st_mtime_ns, etat.st_size

    def _empreinte_disque(self) -> str | None:
        try:
            return hashlib.sha1(self.fichier.read_bytes()).hexdigest()
        except FileNotFoundError:
            return None

    def _charger(self) -> None:
        self._vu = (self._signature(), self._empreinte_disque())
        donnees = stockage.lire_json(self.fichier)
        if donnees is None:
            return
        if not isinstance(donnees, dict) or not isinstance(donnees.get("version_schema", 1), int):
            raise stockage.ErreurStockage(
                "Le fichier « memoire.json » ne contient pas un mémoire lisible. Rien n'a été modifié : "
                "restaure une copie depuis le dossier « sauvegardes »."
            )
        version = donnees.get("version_schema", 1)
        if version > VERSION_SCHEMA:
            raise stockage.ErreurStockage(
                "Ces données ont été enregistrées par une version plus récente de l'outil. "
                "Mets à jour le code sur ce PC (GitHub Desktop → Fetch origin → Pull) "
                "avant de continuer."
            )
        d = dict(donnees)
        d.pop("version_schema", None)
        try:
            projet = d.pop("projet", {})
            self.projet = Projet.depuis_dict(projet)
            if isinstance(projet, dict) and "bibliographie" not in projet:
                self.projet.bibliographie = "trois_parties"  # mémoire créé avant ce réglage : rien ne change pour lui
            self.mots_cles = {m["id"]: MotCle.depuis_dict(m) for m in d.pop("mots_cles", [])}
            self.sources = {s["id"]: Source.depuis_dict(s) for s in d.pop("sources", [])}
            self.extraits = {e["id"]: Extrait.depuis_dict(e) for e in d.pop("extraits", [])}
            self.plan = [Section.depuis_dict(s) for s in d.pop("plan", [])]
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            raise stockage.ErreurStockage(
                "Une entrée de « memoire.json » est illisible (fichier modifié à la main ou abîmé). "
                "Rien n'a été modifié : restaure une copie depuis le dossier « sauvegardes »."
            ) from e
        self.autres = d

    def enregistrer(self) -> None:
        donnees = {
            "version_schema": VERSION_SCHEMA,
            "projet": self.projet.vers_dict(),
            "mots_cles": [m.vers_dict() for m in self.mots_cles.values()],
            "sources": [s.vers_dict() for s in self.sources.values()],
            "extraits": [e.vers_dict() for e in self.extraits.values()],
            "plan": [s.vers_dict() for s in self.plan],
            **self.autres,
        }
        contenu = stockage.serialiser(donnees)
        self._verifier_personne_d_autre(contenu)
        stockage.ecrire_octets(self.fichier, contenu)
        self._vu = (self._signature(), hashlib.sha1(contenu).hexdigest())

    def _verifier_personne_d_autre(self, contenu: bytes) -> None:
        """Ne jamais écraser en silence ce qu'un autre PC a écrit depuis notre dernière lecture.

        Cas visé : le portable resté ouvert à la maison, pendant que l'autre PC a fait
        « Ouvrir quand même » et ajouté des extraits que Drive a synchronisés ici. Ce PC
        n'écrit plus dans memoire.json : son état est mis à l'abri dans « sauvegardes ».
        """
        signature_vue, empreinte_vue = self._vu
        verrou_actuel = verrou.lire(self.dossier)
        autre_pc = bool(verrou_actuel) and verrou_actuel.get("pc") != verrou.nom_pc()
        change = self._signature() != signature_vue and self._empreinte_disque() != empreinte_vue
        if not (autre_pc or change):
            return
        nom = f"memoire_conflit_{verrou.nom_pc()}_{maintenant().replace(':', '-')}.json"
        stockage.ecrire_octets(self.dossier / sauvegardes.NOM_DOSSIER / nom, contenu)
        qui = f"sur {verrou_actuel.get('pc')}" if autre_pc else "sur un autre PC"
        raise stockage.ErreurStockage(
            f"Le mémoire a été ouvert ou modifié {qui} depuis que tu l'as ouvert ici. Pour ne rien écraser, "
            f"cette modification n'a pas été écrite dans memoire.json : ton état actuel est gardé dans "
            f"« sauvegardes/{nom} ». Ferme APAche ici puis rouvre-le pour repartir des données à jour."
        )

    # --- Projet -------------------------------------------------------------

    def modifier_projet(self, reglages_apa: dict | None = None, **changements) -> Projet:
        for cle in changements:
            if cle not in ("titre", "sous_titre", "auteur", "promoteur", "annee_academique", "recherche_en_ligne",
                           "bibliographie"):
                raise DonneesInvalides(f"Champ du projet inconnu : « {cle} ».")
        if "recherche_en_ligne" in changements and not isinstance(changements["recherche_en_ligne"], bool):
            raise DonneesInvalides("« Recherche en ligne » doit être oui ou non.")
        if "bibliographie" in changements and changements["bibliographie"] not in DECOUPAGES_BIBLIOGRAPHIE:
            raise DonneesInvalides("Découpage de bibliographie inconnu.")
        if reglages_apa is not None and not isinstance(reglages_apa, dict):
            raise DonneesInvalides("Réglages de citation illisibles.")
        for cle, valeur in {**changements, **(reglages_apa or {})}.items():
            if cle != "recherche_en_ligne" and not isinstance(valeur, str):
                raise DonneesInvalides(f"« {cle} » doit être du texte.")
        for cle in reglages_apa or {}:
            if cle == "autres" or not hasattr(self.projet.reglages_apa, cle):
                raise DonneesInvalides(f"Réglage de citation inconnu : « {cle} ».")
        for cle, valeur in changements.items():
            setattr(self.projet, cle, valeur if cle == "recherche_en_ligne" else str(valeur))
        for cle, valeur in (reglages_apa or {}).items():
            setattr(self.projet.reglages_apa, cle, str(valeur))
        self.enregistrer()
        return self.projet

    # --- Mots-clés ----------------------------------------------------------

    def _mot_cle(self, id_: str) -> MotCle:
        try:
            return self.mots_cles[id_]
        except (KeyError, TypeError):  # TypeError : un identifiant qui n'est pas du texte
            raise DonneesInvalides("Ce mot-clé n'existe plus (supprimé ou fusionné ?).") from None

    def _verifier_libelle_libre(self, libelle: str, sauf: str | None = None) -> str:
        libelle = libelle.strip() if isinstance(libelle, str) else ""
        if not libelle:
            raise DonneesInvalides("Le mot-clé ne peut pas être vide.")
        for m in self.mots_cles.values():
            if m.id != sauf and m.libelle.casefold() == libelle.casefold():
                raise DonneesInvalides(f"Le mot-clé « {m.libelle} » existe déjà.")
        return libelle

    def _verifier_parent(self, id_: str | None, parent_id: str | None) -> None:
        if parent_id is not None and not isinstance(parent_id, str):
            raise DonneesInvalides("Thème parent illisible.")
        # Remonter depuis le parent proposé : si on retombe sur le mot-clé
        # lui-même, la hiérarchie tournerait en rond.
        courant = parent_id
        while courant is not None:
            if courant == id_:
                raise DonneesInvalides("Un thème ne peut pas être rangé sous lui-même ou sous un de ses sous-thèmes.")
            courant = self._mot_cle(courant).parent_id

    @staticmethod
    def _verifier_couleur(couleur) -> str:
        if not isinstance(couleur, str) or not re.fullmatch(r"(#[0-9a-fA-F]{6})?", couleur):
            raise DonneesInvalides("Couleur illisible (attendu : #rrggbb).")
        return couleur

    @staticmethod
    def _nettoyer_synonymes(synonymes) -> list[str]:
        if synonymes is not None and not isinstance(synonymes, list):
            raise DonneesInvalides("Les synonymes doivent être une liste.")
        propres, vus = [], set()
        for s in synonymes or []:
            s = str(s).strip()
            if s and s.casefold() not in vus:
                vus.add(s.casefold())
                propres.append(s)
        return propres

    def ajouter_mot_cle(self, libelle: str = "", parent_id: str | None = None,
                        synonymes: list[str] | None = None, couleur: str = "") -> MotCle:
        mot = MotCle(libelle=self._verifier_libelle_libre(libelle), parent_id=parent_id or None,
                     synonymes=self._nettoyer_synonymes(synonymes), couleur=self._verifier_couleur(couleur))
        self._verifier_parent(mot.id, parent_id)
        self.mots_cles[mot.id] = mot
        self.enregistrer()
        return mot

    def modifier_mot_cle(self, id_: str, **changements) -> MotCle:
        mot = self._mot_cle(id_)
        for cle in changements:
            if cle not in ("libelle", "parent_id", "synonymes", "couleur"):
                raise DonneesInvalides(f"Champ de mot-clé inconnu : « {cle} ».")
        if "libelle" in changements:
            changements["libelle"] = self._verifier_libelle_libre(changements["libelle"], sauf=id_)
        if "parent_id" in changements:
            changements["parent_id"] = changements["parent_id"] or None
            self._verifier_parent(id_, changements["parent_id"])
        if "synonymes" in changements:
            changements["synonymes"] = self._nettoyer_synonymes(changements["synonymes"])
        if "couleur" in changements:
            self._verifier_couleur(changements["couleur"])
        for cle, valeur in changements.items():
            setattr(mot, cle, valeur)
        self.enregistrer()
        return mot

    def extraits_portant(self, id_: str) -> list[Extrait]:
        return [e for e in self.extraits.values() if id_ in e.mots_cles]

    def supprimer_mot_cle(self, id_: str, confirme: bool = False) -> None:
        mot = self._mot_cle(id_)
        n = len(self.extraits_portant(id_))
        enfants = [m for m in self.mots_cles.values() if m.parent_id == id_]
        if (n or enfants) and not confirme:
            morceaux = []
            if n:
                morceaux.append(f"est utilisé par {_pluriel(n, 'extrait')}, qui le perdront")
            if enfants:
                morceaux.append(f"a {_pluriel(len(enfants), 'sous-thème')}, qui remonteront d'un niveau")
            raise ConfirmationRequise(
                f"Le mot-clé « {mot.libelle} » {' et '.join(morceaux)}. Supprimer quand même ?", n
            )
        for e in self.extraits_portant(id_):
            e.mots_cles.remove(id_)
            e.date_modif = maintenant()
        for m in enfants:
            m.parent_id = mot.parent_id
        for s in self.plan:
            if id_ in s.mots_cles:
                s.mots_cles.remove(id_)
        del self.mots_cles[id_]
        self.enregistrer()

    def fusionner_mots_cles(self, garder_id: str, absorber_id: str) -> MotCle:
        """Le mot-clé absorbé disparaît ; son libellé devient un synonyme du gardé."""
        if garder_id == absorber_id:
            raise DonneesInvalides("Choisis deux mots-clés différents à fusionner.")
        garde, absorbe = self._mot_cle(garder_id), self._mot_cle(absorber_id)
        for synonyme in [absorbe.libelle, *absorbe.synonymes]:
            if synonyme.casefold() not in {s.casefold() for s in [garde.libelle, *garde.synonymes]}:
                garde.synonymes.append(synonyme)
        for e in self.extraits_portant(absorber_id):
            e.mots_cles = [garder_id if m == absorber_id else m for m in e.mots_cles]
            e.mots_cles = list(dict.fromkeys(e.mots_cles))  # sans doublon, ordre conservé
            e.date_modif = maintenant()
        for m in self.mots_cles.values():
            if m.parent_id == absorber_id:
                m.parent_id = garder_id
        if garde.parent_id == absorber_id:
            garde.parent_id = absorbe.parent_id
        for s in self.plan:
            s.mots_cles = list(dict.fromkeys(garder_id if m == absorber_id else m for m in s.mots_cles))
        del self.mots_cles[absorber_id]
        self.enregistrer()
        return garde

    # --- Sources ------------------------------------------------------------

    def _source(self, id_: str) -> Source:
        try:
            return self.sources[id_]
        except (KeyError, TypeError):  # TypeError : un identifiant qui n'est pas du texte
            raise DonneesInvalides("Cette source n'existe plus.") from None

    def ajouter_source(self, source: Source) -> Source:
        source.valider()
        self.sources[source.id] = source
        self.enregistrer()
        return source

    def modifier_source(self, id_: str, **changements) -> Source:
        source = self._source(id_)
        avant = source.vers_dict()
        for cle in changements:
            if cle in ("id", "date_ajout", "date_modif", "autres", "origine_import") or not hasattr(source, cle):
                raise DonneesInvalides(f"Champ de source non modifiable : « {cle} ».")
        for cle, valeur in changements.items():
            setattr(source, cle, valeur)
        try:
            source.valider()
        except DonneesInvalides:
            self.sources[id_] = Source.depuis_dict(avant)
            raise
        source.date_modif = maintenant()
        self.enregistrer()
        return source

    def extraits_de(self, source_id: str) -> list[Extrait]:
        return [e for e in self.extraits.values() if e.source_id == source_id]

    def supprimer_source(self, id_: str, confirme: bool = False) -> None:
        source = self._source(id_)
        extraits = self.extraits_de(id_)
        if extraits and not confirme:
            raise ConfirmationRequise(
                f"La source « {source.titre or 'sans titre'} » a {_pluriel(len(extraits), 'extrait')}, "
                f"qui seront supprimés avec elle. Supprimer quand même ?",
                len(extraits),
            )
        for e in extraits:
            del self.extraits[e.id]
        del self.sources[id_]
        self.enregistrer()

    # --- Extraits -----------------------------------------------------------

    def _extrait(self, id_: str) -> Extrait:
        try:
            return self.extraits[id_]
        except (KeyError, TypeError):  # TypeError : un identifiant qui n'est pas du texte
            raise DonneesInvalides("Cet extrait n'existe plus.") from None

    def _verifier_extrait(self, extrait: Extrait) -> None:
        extrait.valider()
        extrait.texte = mise_en_forme.nettoyer(extrait.texte)
        self._source(extrait.source_id)
        if extrait.section_plan:
            self._section(extrait.section_plan)
        for m in extrait.mots_cles:
            self._mot_cle(m)

    def ajouter_extrait(self, extrait: Extrait) -> Extrait:
        self._verifier_extrait(extrait)
        self.extraits[extrait.id] = extrait
        self.enregistrer()
        return extrait

    def modifier_extrait(self, id_: str, **changements) -> Extrait:
        extrait = self._extrait(id_)
        avant = extrait.vers_dict()
        for cle in changements:
            if cle in ("id", "date_ajout", "date_modif", "autres", "origine_import") or not hasattr(extrait, cle):
                raise DonneesInvalides(f"Champ d'extrait non modifiable : « {cle} ».")
        for cle, valeur in changements.items():
            setattr(extrait, cle, valeur)
        try:
            self._verifier_extrait(extrait)
        except DonneesInvalides:
            # Ne pas laisser en mémoire un extrait invalide qui serait écrit
            # à la prochaine modification d'autre chose.
            self.extraits[id_] = Extrait.depuis_dict(avant)
            raise
        extrait.date_modif = maintenant()
        self.enregistrer()
        return extrait

    def supprimer_extrait(self, id_: str) -> None:
        self._extrait(id_)
        del self.extraits[id_]
        self.enregistrer()

    # --- Plan ---------------------------------------------------------------

    def _section(self, id_: str) -> Section:
        for s in self.plan:
            if s.id == id_:
                return s
        raise DonneesInvalides("Cette partie du plan n'existe plus.")

    def _verifier_section(self, section: Section) -> None:
        section.valider()
        for m in section.mots_cles:
            self._mot_cle(m)

    def ajouter_section(self, titre: str = "", niveau: int = 1, mots_cles: list[str] | None = None,
                        apres: str | None = None) -> Section:
        if mots_cles is not None and not isinstance(mots_cles, list):
            raise DonneesInvalides("Liste de mots-clés illisible.")
        if apres is not None and not isinstance(apres, str):
            raise DonneesInvalides("Position dans le plan illisible.")
        section = Section(titre=titre.strip() if isinstance(titre, str) else "", niveau=niveau, mots_cles=list(mots_cles or []))
        self._verifier_section(section)
        position = len(self.plan) if apres is None else self.plan.index(self._section(apres)) + 1
        self.plan.insert(position, section)
        self.enregistrer()
        return section

    def modifier_section(self, id_: str, **changements) -> Section:
        section = self._section(id_)
        avant = section.vers_dict()
        for cle in changements:
            if cle not in ("titre", "niveau", "mots_cles"):
                raise DonneesInvalides(f"Champ du plan non modifiable : « {cle} ».")
        for cle, valeur in changements.items():
            setattr(section, cle, valeur.strip() if cle == "titre" and isinstance(valeur, str) else valeur)
        try:
            self._verifier_section(section)
        except DonneesInvalides:
            self.plan[self.plan.index(section)] = Section.depuis_dict(avant)
            raise
        self.enregistrer()
        return section

    def _bloc(self, debut: int) -> tuple[int, int]:
        """Un chapitre et ses sections forment un bloc [debut, fin[ ; une section est seule."""
        fin = debut + 1
        if self.plan[debut].niveau == 1:
            while fin < len(self.plan) and self.plan[fin].niveau == 2:
                fin += 1
        return debut, fin

    def deplacer_section(self, id_: str, sens: str) -> None:
        """Monter ou descendre d'un cran. Un chapitre passe avec ses sections par-dessus
        le chapitre voisin, entier : ses sections ne changent jamais de chapitre en route.
        Une section, elle, peut passer d'un chapitre à l'autre."""
        if sens not in ("haut", "bas"):
            raise DonneesInvalides("Sens de déplacement inconnu.")
        i = self.plan.index(self._section(id_))
        debut, fin = self._bloc(i)
        bloc = self.plan[debut:fin]
        if self.plan[i].niveau == 2:
            j = i - 1 if sens == "haut" else i + 1
            if 0 <= j < len(self.plan):
                self.plan[i], self.plan[j] = self.plan[j], self.plan[i]
        elif sens == "haut":
            precedent = next((k for k in range(debut - 1, -1, -1) if self.plan[k].niveau == 1), None)
            if precedent is not None:
                self.plan[precedent:fin] = bloc + self.plan[precedent:debut]
        else:
            if fin < len(self.plan):
                _, fin_suivant = self._bloc(fin)
                self.plan[debut:fin_suivant] = self.plan[fin:fin_suivant] + bloc
        self.enregistrer()

    def supprimer_section(self, id_: str, confirme: bool = False) -> None:
        section = self._section(id_)
        ranges = [e for e in self.extraits.values() if e.section_plan == id_]
        if ranges and not confirme:
            raise ConfirmationRequise(
                f"« {section.titre} » a {_pluriel(len(ranges), 'extrait')} rangé{'s' if len(ranges) > 1 else ''} à la main ; "
                f"{'ils' if len(ranges) > 1 else 'il'} ne seront plus dans le plan, mais restent dans la grille. Supprimer quand même ?",
                len(ranges))
        for e in ranges:
            e.section_plan = None
            e.date_modif = maintenant()
        self.plan.remove(section)
        self.enregistrer()

    def numeros_du_plan(self) -> dict[str, str]:
        """1, 1.1, 1.2, 2… d'après l'ordre et le niveau ; une section avant tout chapitre compte en 0.x."""
        numeros, chapitre, section = {}, 0, 0
        for s in self.plan:
            if s.niveau == 1:
                chapitre, section = chapitre + 1, 0
                numeros[s.id] = str(chapitre)
            else:
                section += 1
                numeros[s.id] = f"{chapitre}.{section}"
        return numeros

    # --- Fichiers joints -----------------------------------------------------

    def chemin_fichier(self, source: Source) -> Path | None:
        if not source.fichier_joint:
            return None
        chemin = (self.dossier / source.fichier_joint).resolve()
        # Un chemin relatif trafiqué ne doit jamais sortir du dossier de données.
        if self.dossier.resolve() not in chemin.parents:
            return None
        return chemin

    def joindre_fichier(self, id_: str, nom: str, contenu: bytes) -> Source:
        """Copie le fichier dans « fichiers/ » du dossier de données et le rattache
        à la source. L'original de l'utilisateur n'est jamais touché ; une copie
        jointe auparavant à cette source est remplacée."""
        source = self._source(id_)
        extension = fichiers.verifier_fichier(nom, contenu)
        propre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(nom).stem).strip(" .")[:80] or "document"
        relatif = f"{DOSSIER_FICHIERS}/{propre}-{source.id}{extension}"
        stockage.ecrire_octets(self.dossier / relatif, contenu)
        ancien = self.chemin_fichier(source)
        source.fichier_joint = relatif
        source.premiere_page = ""  # nouveau fichier : sa numérotation reste à établir
        source.date_modif = maintenant()
        self.enregistrer()
        if ancien and ancien != (self.dossier / relatif).resolve() and ancien.exists():
            ancien.unlink()
        return source

    # --- Import -------------------------------------------------------------

    def ajouter_en_lot(self, mots_cles: list[MotCle], sources: list[Source], extraits: list[Extrait]) -> None:
        """Un seul enregistrement pour tout un import : des centaines d'écritures
        successives seraient lentes sur Drive, et une coupure laisserait un
        import à moitié fait. Tout est vérifié avant d'ajouter quoi que ce soit."""
        for s in sources:
            s.valider()
        ids_mots = set(self.mots_cles) | {m.id for m in mots_cles}
        ids_sources = set(self.sources) | {s.id for s in sources}
        for e in extraits:
            e.valider()
            if e.source_id not in ids_sources or not set(e.mots_cles) <= ids_mots:
                raise DonneesInvalides("Import incohérent : un extrait renvoie à une source ou un mot-clé absent. "
                                       "Rien n'a été importé.")
        for m in mots_cles:
            self.mots_cles[m.id] = m
        for s in sources:
            self.sources[s.id] = s
        for e in extraits:
            self.extraits[e.id] = e
        self.enregistrer()
