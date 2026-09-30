"""Fichiers joints aux sources : texte des PDF et des Word, page par page.

La page d'un PDF n'est pas la page imprimée : la première page d'un article
d'une revue est souvent la page 953. Une citation doit porter la page imprimée,
d'où la numérotation, par ordre de confiance :
1. celle que l'utilisateur a indiquée (« la page 1 du PDF est la page 953 ») ;
2. celle inscrite dans le PDF (/PageLabels), quand l'éditeur l'a mise ;
3. les numéros lus dans les en-têtes et pieds de page, s'ils se suivent ;
4. à défaut, la numérotation du PDF (1, 2, 3…), signalée comme à vérifier.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

from . import stockage
from .modele import DonneesInvalides

EXTENSIONS = {".pdf": "application/pdf",
              ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
TAILLE_MAX = 200 * 1024 * 1024
# En dessous de ce nombre de caractères par page en moyenne, le PDF est une image scannée.
CARACTERES_MIN_PAR_PAGE = 25

_cache: dict[tuple, dict] = {}  # (chemin, date, taille) → pages lues : relire un gros PDF prend des secondes


def verifier_fichier(nom: str, contenu: bytes) -> str:
    """L'extension à garder, ou une erreur qui dit quoi faire."""
    extension = Path(nom).suffix.lower()
    if extension == ".doc":
        raise DonneesInvalides("Les anciens fichiers Word (.doc) ne sont pas lus : ouvre-le dans Word et "
                               "enregistre-le au format .docx, puis glisse ce nouveau fichier.")
    if extension not in EXTENSIONS:
        raise DonneesInvalides(f"« {nom} » n'est ni un PDF ni un Word (.docx) : l'outil ne sait pas le lire.")
    if len(contenu) > TAILLE_MAX:
        raise DonneesInvalides(f"« {nom} » dépasse {TAILLE_MAX // (1024 * 1024)} Mo : trop lourd pour être joint.")
    signature = b"%PDF" if extension == ".pdf" else b"PK"
    if not contenu[:1024].lstrip().startswith(signature):
        raise DonneesInvalides(f"« {nom} » porte l'extension {extension} mais n'en est pas un : le fichier est peut-être abîmé.")
    return extension


# --- Lecture --------------------------------------------------------------------------

def _lire_pdf(chemin: Path) -> dict:
    from pypdf import PdfReader  # importé ici : l'outil démarre même si pypdf manque

    try:
        lecteur = PdfReader(str(chemin))
        if lecteur.is_encrypted and not lecteur.decrypt(""):
            raise DonneesInvalides("Ce PDF est protégé par un mot de passe : l'outil ne peut pas en lire le texte. "
                                   "Il reste joint à la source ; saisis tes extraits à la main.")
        textes = []
        for page in lecteur.pages:
            try:
                textes.append(page.extract_text() or "")
            except Exception:  # une page abîmée ne doit pas empêcher de lire les autres
                textes.append("")
        racine = lecteur.trailer["/Root"]
        etiquettes = list(lecteur.page_labels) if "/PageLabels" in racine else None
    except DonneesInvalides:
        raise
    except Exception:  # PdfReadError, AES sans le paquet cryptography, structure inattendue…
        return _lire_pdf_pdfium(chemin)
    return {"type": "pdf", "textes": textes, "etiquettes_pdf": etiquettes}


def _lire_pdf_pdfium(chemin: Path) -> dict:
    """Second lecteur, quand pypdf renonce : PDFium (le moteur de Chrome, déjà là pour l'OCR)
    ouvre la plupart des PDF d'éditeurs chiffrés sans mot de passe, et bien des PDF abîmés."""
    illisible = DonneesInvalides("Ce PDF est abîmé, protégé par un mot de passe, ou d'un format que l'outil ne sait "
                                 "pas lire. Il reste joint à la source ; saisis tes extraits à la main.")
    try:
        import pypdfium2
    except ImportError:
        raise illisible from None
    try:
        document = pypdfium2.PdfDocument(str(chemin))
    except Exception:
        raise illisible from None
    try:
        textes, etiquettes = [], []
        for i in range(len(document)):
            try:
                textes.append(document[i].get_textpage().get_text_range() or "")
            except Exception:
                textes.append("")
            try:
                etiquettes.append(document.get_page_label(i) or "")
            except Exception:
                etiquettes.append("")
    finally:
        document.close()
    return {"type": "pdf", "textes": [t.replace("\r\n", "\n") for t in textes],
            "etiquettes_pdf": etiquettes if any(etiquettes) else None}


def _lire_docx(chemin: Path) -> dict:
    from .import_extraits import W, ouvrir_docx  # ici : import_extraits dépend de depot, qui dépend de ce module

    document, _ = ouvrir_docx(chemin)
    paragraphes = ["".join(t.text or "" for t in p.iter(W + "t")) for p in document.iter(W + "p")]
    return {"type": "docx", "textes": ["\n\n".join(p for p in paragraphes if p.strip())], "etiquettes_pdf": None}


def empreinte(chemin: Path) -> str:
    h = hashlib.sha1()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()[:20]


def _lire(chemin: Path, dossier_index: Path | None = None) -> dict:
    """Le texte lu du fichier. Gardé en mémoire le temps de la séance, et sur le disque
    (dossier_index) d'une séance à l'autre : relire 60 PDF à chaque recherche prendrait des minutes.
    La copie sur le disque est rattachée au contenu du fichier : un fichier remplacé est relu."""
    etat = chemin.stat()
    cle = (str(chemin), etat.st_mtime_ns, etat.st_size)
    if cle not in _cache and dossier_index is not None:
        fiche = chemin_index(chemin, dossier_index)
        lu = stockage.lire_json(fiche) if fiche.exists() else None
        if lu is None:
            lu = _lire_pdf(chemin) if chemin.suffix.lower() == ".pdf" else _lire_docx(chemin)
            stockage.ecrire_json(fiche, lu)
        _cache[cle] = lu
    if cle not in _cache:
        if len(_cache) > 20:
            _cache.clear()
        _cache[cle] = _lire_pdf(chemin) if chemin.suffix.lower() == ".pdf" else _lire_docx(chemin)
    return _cache[cle]


# --- Numérotation ------------------------------------------------------------------------

def decalage_des_entetes(textes: list[str]) -> int | None:
    """Décalage d tel que la page d'indice i porte le numéro i + d dans ses
    en-têtes ou pieds de page, si une majorité de pages l'atteste."""
    votes = Counter()
    for i, texte in enumerate(textes):
        lignes = [l.strip() for l in texte.splitlines() if l.strip()]
        numeros = set()
        for ligne in lignes[:3] + lignes[-3:]:
            # Un nombre seul, pas une partie de date (« 2017 » varie d'une page à l'autre : il ne votera pas ensemble).
            numeros.update(int(m) for m in re.findall(r"(?<![\d.,:/-])(\d{1,4})(?![\d.,:/-])", ligne))
        votes.update(n - i for n in numeros)
    if not votes or len(textes) < 2:
        return None
    decalage, nombre = votes.most_common(1)[0]
    return decalage if nombre >= max(2, 0.6 * len(textes)) else None


def chemin_index(chemin: Path, dossier_index: Path) -> Path:
    return Path(dossier_index) / f"{empreinte(chemin)}.json"


def deja_lu(chemin: Path, dossier_index: Path) -> bool:
    etat = chemin.stat()
    return (str(chemin), etat.st_mtime_ns, etat.st_size) in _cache or chemin_index(chemin, dossier_index).exists()


def texte_du_fichier(chemin: Path, premiere_page: str = "", dossier_index: Path | None = None) -> dict:
    lu = _lire(chemin, dossier_index)
    textes = lu["textes"]
    if lu["type"] == "docx":
        return {"type": "docx", "numerotation": "aucune", "premiere": "", "scanne": False,
                "pages": [{"etiquette": "", "texte": textes[0]}]}

    caracteres = sum(len(t.strip()) for t in textes)
    scanne = caracteres < CARACTERES_MIN_PAR_PAGE * max(1, len(textes))
    decalage = decalage_des_entetes(textes)
    simple = [str(i + 1) for i in range(len(textes))]
    # Une numérotation du PDF qui répète 1, 2, 3… n'apprend rien : les en-têtes passent avant.
    etiquettes_pdf = lu["etiquettes_pdf"] if lu["etiquettes_pdf"] != simple else None
    if premiere_page.strip().isdigit():
        etiquettes, numerotation = [str(int(premiere_page) + i) for i in range(len(textes))], "manuelle"
    elif etiquettes_pdf and any(e.isdigit() for e in etiquettes_pdf):
        etiquettes, numerotation = etiquettes_pdf, "pdf"
    elif decalage is not None:
        etiquettes, numerotation = [str(i + decalage) for i in range(len(textes))], "entetes"
    else:
        etiquettes, numerotation = [str(i + 1) for i in range(len(textes))], "a_verifier"
    # Couverture, sommaire… avant la page 1 imprimée : pas de numéro plutôt que « page -2 ».
    etiquettes = ["" if e.lstrip("-").isdigit() and int(e) < 1 else e for e in etiquettes]
    premiere = next((i for i, e in enumerate(etiquettes) if e), None)
    ocr = lu.get("ocr") or [False] * len(textes)
    return {"type": "pdf", "numerotation": numerotation, "scanne": scanne,
            "premiere": etiquettes[premiere] if premiere is not None else "",
            "premiere_pdf": premiere + 1 if premiere is not None else 1,  # page du PDF qui porte ce numéro
            # Pages encore sans texte (images) que l'OCR pourrait lire, et pages déjà lues ainsi.
            "pages_vides": sum(len(t.strip()) < CARACTERES_MIN_PAR_PAGE and not o for t, o in zip(textes, ocr)),
            "pages_ocr": sum(ocr),
            "pages": [{"etiquette": e, "texte": t, "ocr": o} for e, t, o in zip(etiquettes, textes, ocr)]}
