# Fabrication d'APAche.exe : « python -m PyInstaller APAche.spec » (voir le mode d'emploi, section Développement).
# Résultat : dist/APAche/, un dossier à zipper ; rien à installer chez l'utilisateur.
from PyInstaller.utils.hooks import collect_all

donnees = [("memoire/interface", "memoire/interface")]
binaires, caches = [], []
for paquet in ("pypdfium2", "pypdfium2_raw"):  # moteur PDF (fichiers abîmés ou chiffrés, OCR) et sa DLL
    d, b, c = collect_all(paquet)
    donnees += d
    binaires += b
    caches += c

a = Analysis(["APAche.py"], datas=donnees, binaries=binaires, hiddenimports=caches,
             excludes=["tkinter", "unittest", "pytest", "playwright"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="APAche",
          console=True,  # la fenêtre noire : la fermer ferme APAche proprement (sauvegarde, verrou)
          icon=None, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="APAche", upx=False)
