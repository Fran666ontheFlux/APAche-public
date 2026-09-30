# APAche

**Tes sources, tes extraits et tes citations APA au même endroit, sur ton PC, sans compte ni abonnement.**

APAche aide à écrire un mémoire (ou tout travail de recherche) : tu ranges tes lectures,
tu en gardes les passages utiles avec leur page, tu les classes par thèmes, et l'outil
écrit pour toi les citations et la bibliographie aux normes APA 7, prêtes à coller dans
Google Docs ou Word.

Gratuit et libre (licence MIT). Tout reste sur ton ordinateur : rien n'est envoyé sur internet.

## Ce que fait APAche

- **Sources** : livres, articles, chapitres, rapports, pages web, textes légaux… La référence
  APA se construit pendant que tu remplis la fiche ; l'outil signale ce qui manque.
  Un DOI ou un ISBN suffit pour remplir la fiche (si tu l'autorises, voir Confidentialité).
- **Extraits** : glisse le PDF ou le Word d'une source, sélectionne un passage, appuie sur
  `N` : l'extrait est créé avec le bon numéro de page (même quand la revue commence page 953).
  Gras et italique au clavier (`Ctrl+G` ou `Ctrl+B`, `Ctrl+I`).
- **Citations prêtes à copier** : (Martin, 2020, p. 45), la forme narrative, ou « passage » (Martin, 2020, p. 45).
- **Mots-clés et plan** : classe tes extraits par thèmes, vois ce qui manque (onglet
  « Couverture »), range-les dans les parties de ton plan.
- **Recherche** dans tes extraits et dans le texte de tous tes PDF joints.
- **PDF scannés** : lecture du texte par OCR (avec Tesseract, voir plus bas).
- **Bibliographie finale** : seulement les sources vraiment citées, en une liste APA ou en
  trois parties (références scientifiques, sources non scientifiques, sitographie).
  Export RIS (Zotero, Mendeley, Word) et BibTeX (LaTeX).
- **Import** : une bibliographie Word existante, des notes de lecture dans un Google Doc à
  onglets, ou tes dossiers de PDF « à lire » et « lus ».

## Installer (Windows)

1. Va dans [**Releases**](../../releases) et télécharge le dernier `APAche-…-windows.zip`.
2. Décompresse-le où tu veux (par exemple dans `Documents`) : clic droit → « Extraire tout ».
3. Ouvre le dossier `APAche` et double-clique sur **`APAche.exe`**.

Rien d'autre à installer. Au premier lancement, Windows peut afficher « Windows a protégé
votre ordinateur » : APAche n'est pas signé (la signature est payante). Clique sur
« Informations complémentaires », puis « Exécuter quand même ».

Une fenêtre noire s'ouvre, puis ton navigateur. **Laisse la fenêtre noire ouverte** pendant
que tu travailles : la fermer ferme APAche (après avoir tout sauvegardé).

## Premier lancement

APAche te demande un **dossier de données** : c'est là qu'il range ta bibliothèque (sources, extraits), les fichiers
que tu joins et les sauvegardes. Crée un dossier vide, par exemple `Documents\Mon mémoire`,
et colle son chemin (dans l'Explorateur : clic droit sur le dossier → « Copier en tant que
chemin d'accès »).

**Sur plusieurs PC** (portable et fixe) : choisis un dossier synchronisé (Google Drive pour
ordinateur, OneDrive, Dropbox…) et le même dossier sur chaque PC. APAche prévient si le
mémoire est déjà ouvert ailleurs, et n'écrase jamais en silence ce qu'un autre PC a modifié.

## Sauvegardes

Chaque jour d'utilisation et à chaque fermeture, une copie datée est rangée dans
`sauvegardes/` (les 30 dernières). Pour revenir en arrière : ferme APAche, remplace
`memoire.json` par une de ces copies, relance.

## Lire les PDF scannés (facultatif)

Pour les PDF qui ne sont que des images (scans, photos de livres), installe
[Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) :

- avec l'installateur de la page ci-dessus, en cochant **French** dans « Additional language data » ;
- ou, dans un terminal : `winget install UB-Mannheim.TesseractOCR`, puis télécharge
  [`fra.traineddata`](https://github.com/tesseract-ocr/tessdata/raw/main/fra.traineddata)
  dans `%LOCALAPPDATA%\APAche\tessdata` (crée le dossier s'il n'existe pas).

Relance APAche : un bouton « Lire le texte par OCR » apparaît sur les PDF scannés.

## Confidentialité

APAche fonctionne entièrement sur ton PC : son petit serveur n'écoute que ton ordinateur,
refuse toute page d'un autre site, et n'envoie rien sur internet. Une seule exception, que
tu actives toi-même (Projet → Confidentialité) : compléter une référence depuis son DOI ou
son ISBN. Seul cet identifiant part alors, et seulement quand tu cliques, vers CrossRef,
Open Library ou le catalogue de la BnF.

## Réglages utiles

- **Projet → Citations** : les petits mots des citations (« et » ou « & », « s. d. », « cité dans »…),
  à ajuster selon le guide APA de ton université.
- **Bibliographie** : une seule liste (norme APA) ou trois parties.

## Pour les développeurs

Python 3.12 ou plus récent.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python -m memoire          # ou double-clic sur « Ouvrir APAche.bat »
.venv\Scripts\python -m pytest -q        # les tests
.venv\Scripts\python -m PyInstaller APAche.spec   # fabrique dist\APAche\APAche.exe
```

Le code est en français, comme l'interface. `memoire/` contient le serveur local et les
règles APA (`apa.py`), `memoire/interface/` la page web, `tests/` les tests.
Une nouvelle version publique : `git tag v1.2.0` puis `git push origin v1.2.0` ; GitHub
fabrique le `.zip` et le publie dans Releases (voir `.github/workflows/version.yml`).

## Licence

[MIT](LICENSE) © 2026 Fran666ontheFlux. Tu peux l'utiliser, le modifier et le partager
librement.

APAche n'a aucun lien avec l'Apache Software Foundation ni avec l'American Psychological
Association : le nom est un clin d'œil aux normes APA.
