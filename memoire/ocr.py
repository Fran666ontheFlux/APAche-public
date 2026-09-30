"""Lire le texte d'un PDF scanné par reconnaissance de caractères (OCR).

Deux outils, tous deux sur le PC, sans internet :
- pypdfium2 transforme chaque page en image (le moteur PDF de Chrome, un seul paquet) ;
- Tesseract, programme installé à part (Windows : « winget install UB-Mannheim.TesseractOCR »),
  lit l'image. Les langues française et anglaise sont cherchées d'abord dans le dossier de
  l'utilisateur (%LOCALAPPDATA%/APAche/tessdata), qui ne demande pas de droits d'administrateur.

L'OCR est lente (quelques secondes par page) : elle avance par tranches pour que l'interface
montre la progression, et chaque page lue est gardée avec le texte du fichier (index/).
Sans Tesseract, l'outil le dit et fonctionne comme avant.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import fichiers, stockage
from .modele import DonneesInvalides

RESOLUTION = 300          # points par pouce : ce qu'il faut à Tesseract pour du texte courant
BUDGET = 4.0              # secondes d'OCR par appel, entre deux mises à jour de la progression
LANGUES_VOULUES = ("fra", "eng")
PAGE_VIDE = fichiers.CARACTERES_MIN_PAR_PAGE
MARGE = 0.08              # part de la hauteur relue en haut et en bas, pour le numéro de page
# Mots très fréquents, pour reconnaître un document anglais : lu avec les deux langues à la
# fois, Tesseract perd les accents français (« Héléne », « a » pour « à ») ; on en choisit une.
MOTS_ANGLAIS = {"the", "and", "of", "to", "is", "that", "in", "for", "with", "are", "this", "which", "from"}
MOTS_FRANCAIS = {"le", "la", "les", "et", "des", "du", "est", "une", "que", "dans", "pour", "qui", "sur"}


def _dossier_langues_utilisateur() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    ancien = base / "memoire-outil" / "tessdata"  # nom des premières versions, encore lu
    return ancien if ancien.is_dir() and not (base / "APAche" / "tessdata").is_dir() else base / "APAche" / "tessdata"


def _executable() -> str | None:
    candidats = [shutil.which("tesseract"),
                 r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                 r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                 str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe")]
    return next((c for c in candidats if c and Path(c).is_file()), None)


def _sans_fenetre() -> dict:
    # Sous Windows, ne pas faire clignoter une fenêtre noire à chaque page.
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def outil() -> dict:
    """Ce qui est disponible : {"disponible", "message", et pour l'usage "exe", "tessdata", "langues"}."""
    exe = _executable()
    if not exe:
        return {"disponible": False, "message": "Tesseract n'est pas installé sur ce PC. Pour lire les PDF scannés : "
                "winget install UB-Mannheim.TesseractOCR, puis relance l'outil."}
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return {"disponible": False, "message": "Il manque le paquet pypdfium2 : relance « Ouvrir APAche.bat », "
                "qui l'installe (une connexion à internet est nécessaire cette fois-là)."}
    tessdata = _dossier_langues_utilisateur()
    commande = [exe, "--list-langs"] + (["--tessdata-dir", str(tessdata)] if tessdata.is_dir() else [])
    try:
        sortie = subprocess.run(commande, capture_output=True, text=True, timeout=20, **_sans_fenetre())
    except (OSError, subprocess.TimeoutExpired):
        return {"disponible": False, "message": "Tesseract est installé mais ne répond pas."}
    presentes = {ligne.strip() for ligne in (sortie.stdout + sortie.stderr).splitlines()}
    langues = [l for l in LANGUES_VOULUES if l in presentes]
    if not langues:
        return {"disponible": False, "message": "Tesseract est installé sans les langues française ni anglaise."}
    message = "" if "fra" in langues else "Français absent : l'OCR lira en anglais, les accents seront mal reconnus."
    return {"disponible": True, "message": message, "exe": exe, "langues": langues,
            "tessdata": str(tessdata) if tessdata.is_dir() else None}


def _pgm(chemin: Path, largeur: int, lignes: list[bytes]) -> Path:
    chemin.write_bytes(b"P5 %d %d 255\n" % (largeur, len(lignes)) + b"".join(lignes))
    return chemin


def _images_de_page(chemin_pdf: Path, index: int, dossier: Path) -> tuple[Path, Path, Path]:
    """Page du PDF → images en niveaux de gris (format PGM, que Tesseract lit sans autre
    bibliothèque) : la page entière, sa marge du haut et sa marge du bas."""
    import pypdfium2

    document = pypdfium2.PdfDocument(str(chemin_pdf))
    try:
        image = document[index].render(scale=RESOLUTION / 72, grayscale=True)
        largeur, hauteur, pas = image.width, image.height, image.stride
        octets = bytes(image.buffer)
        lignes = [octets[y * pas:y * pas + largeur] for y in range(hauteur)]
    finally:
        document.close()
    marge = max(1, int(hauteur * MARGE))
    return (_pgm(dossier / f"page-{index}.pgm", largeur, lignes),
            _pgm(dossier / f"haut-{index}.pgm", largeur, lignes[:marge]),
            _pgm(dossier / f"bas-{index}.pgm", largeur, lignes[-marge:]))


def _tesseract(image: Path, langue: str, reglages: dict, index: int, bloc: bool = False) -> str:
    commande = [reglages["exe"], str(image), "stdout", "-l", langue]
    if bloc:  # un seul bloc : un numéro isolé dans un coin n'est pas écarté comme une tache
        commande += ["--psm", "6"]
    if reglages.get("tessdata"):
        commande += ["--tessdata-dir", reglages["tessdata"]]
    try:
        resultat = subprocess.run(commande, capture_output=True, timeout=180, **_sans_fenetre())
    except subprocess.TimeoutExpired:
        raise DonneesInvalides(f"La page {index + 1} a pris trop de temps à lire.") from None
    return resultat.stdout.decode("utf-8", errors="replace").strip()


def langue_du_texte(texte: str, langues: list[str]) -> str:
    if len(langues) == 1:
        return langues[0]
    mots = re.findall(r"[a-z]+", texte.casefold())
    anglais, francais = sum(m in MOTS_ANGLAIS for m in mots), sum(m in MOTS_FRANCAIS for m in mots)
    return "eng" if anglais > francais else "fra"


def numero_seul(texte: str) -> str:
    """Le numéro de page lu dans une marge, s'il n'y a que lui (« 12 », « - 12 - »)."""
    m = re.fullmatch(r"\W*(\d{1,4})\W*", texte.strip())
    return m.group(1) if m else ""


def lire_page(chemin_pdf: Path, index: int, reglages: dict, langue: str | None = None) -> tuple[str, str]:
    """Texte de la page, et la langue dans laquelle il a été lu : le français d'abord,
    l'anglais si le texte se révèle anglais (quand la langue du document n'est pas encore choisie)."""
    with tempfile.TemporaryDirectory(prefix="memoire-ocr-") as dossier:  # les images sont effacées aussitôt lues
        page, haut, bas = _images_de_page(chemin_pdf, index, Path(dossier))
        langues = reglages["langues"]
        texte = _tesseract(page, langue or langues[0], reglages, index)
        if langue is None:
            langue = langue_du_texte(texte, langues)
            if langue != langues[0]:
                texte = _tesseract(page, langue, reglages, index)
        # Le numéro imprimé, petit et seul dans un coin, échappe souvent à la lecture de la
        # page entière ; relu à part, il rejoint le texte pour que la numérotation le trouve.
        lignes = [l.strip() for l in texte.splitlines() if l.strip()]
        haut, bas = (numero_seul(_tesseract(image, langue, reglages, index, bloc=True)) for image in (haut, bas))
        if haut and haut not in lignes[:3]:
            texte = f"{haut}\n\n{texte}"
        if bas and bas not in lignes[-3:]:
            texte = f"{texte}\n\n{bas}"
    return re.sub(r"\n\s*\n", "\n\n", texte).strip(), langue


def avancer(chemin_pdf: Path, dossier_index: Path) -> dict:
    """Lit par OCR les pages sans texte, dans la limite du budget. Renvoie la progression."""
    reglages = outil()
    if not reglages["disponible"]:
        raise DonneesInvalides(reglages["message"])
    if chemin_pdf.suffix.lower() != ".pdf":
        raise DonneesInvalides("L'OCR ne concerne que les PDF.")
    lu = fichiers._lire(chemin_pdf, dossier_index)
    ocr = lu.setdefault("ocr", [False] * len(lu["textes"]))
    a_lire = [i for i, t in enumerate(lu["textes"]) if len(t.strip()) < PAGE_VIDE and not ocr[i]]
    debut, faites = time.monotonic(), 0
    for i in a_lire:
        if faites and time.monotonic() - debut > BUDGET:
            break
        # Une langue par document, choisie à la première page lue.
        lu["textes"][i], lu["ocr_langue"] = lire_page(chemin_pdf, i, reglages, lu.get("ocr_langue"))
        ocr[i] = True
        faites += 1
    if faites:
        stockage.ecrire_json(fichiers.chemin_index(chemin_pdf, dossier_index), lu)
    return {"faites": sum(ocr), "restantes": len(a_lire) - faites, "total": sum(ocr) + len(a_lire) - faites}
