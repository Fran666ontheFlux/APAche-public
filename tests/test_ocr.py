"""OCR des PDF scannés. Les tests qui lisent vraiment une image demandent Tesseract :
sans lui (autre PC, intégration continue), ils vérifient seulement que l'outil le dit clairement."""

from pathlib import Path

from outils import dossier_temporaire, lancer

from memoire import fichiers, ocr, recherche
from memoire.depot import Memoire
from memoire.modele import DonneesInvalides, Source
from test_fichiers import pdf


def pdf_scanne(dossier: Path, lignes_par_page: list[list[str]]) -> bytes:
    """Un vrai PDF « scanné » : chaque page n'est qu'une image, sans aucun texte dedans."""
    import pypdfium2

    source = pypdfium2.PdfDocument(pdf(lignes_par_page))
    scanne = pypdfium2.PdfDocument.new()
    for page in source:
        largeur, hauteur = page.get_size()
        image = page.render(scale=200 / 72, grayscale=True)
        nouvelle = scanne.new_page(largeur, hauteur)
        objet = pypdfium2.PdfImage.new(scanne)
        objet.set_bitmap(image)
        objet.set_matrix(pypdfium2.PdfMatrix().scale(largeur, hauteur))
        nouvelle.insert_obj(objet)
        nouvelle.gen_content()
    chemin = dossier / "scan.pdf"
    scanne.save(str(chemin))
    source.close()
    scanne.close()
    return chemin.read_bytes()


def test_outil_dit_ce_qui_est_disponible():
    etat = ocr.outil()
    assert set(etat) >= {"disponible", "message"}
    if not etat["disponible"]:
        assert "Tesseract" in etat["message"] or "pypdfium2" in etat["message"]


def test_pdf_scanne_lu_par_ocr():
    if not ocr.outil()["disponible"]:
        print("    (Tesseract absent : test sauté)")
        return
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        s = m.ajouter_source(Source(type="livre", titre="Scan", champs={"editeur": "E"}))
        pages = [["La création des jardins partagés", "transforme les quartiers populaires."],
                 ["Les composts collectifs", "précèdent souvent la végétalisation.", "", "", "", "", "", "", "", "", "", "12"]]
        m.joindre_fichier(s.id, "scan.pdf", pdf_scanne(Path(d), pages))
        chemin, index = m.chemin_fichier(s), Path(d) / recherche.DOSSIER_INDEX
        avant = fichiers.texte_du_fichier(chemin, "", index)
        assert avant["scanne"] and avant["pages_vides"] == 2  # rien de lisible sans OCR

        etat = {"restantes": 1}
        while etat["restantes"]:
            etat = ocr.avancer(chemin, index)
        assert etat == {"faites": 2, "restantes": 0, "total": 2}

        apres = fichiers.texte_du_fichier(chemin, "", index)
        assert not apres["scanne"] and apres["pages_ocr"] == 2 and apres["pages_vides"] == 0
        texte = " ".join(p["texte"] for p in apres["pages"]).casefold()
        for mot in ("création", "jardins", "partagés", "composts", "végétalisation", "précèdent"):
            assert mot in texte, (mot, texte)  # le français, accents compris
        # Le texte lu est gardé : la recherche le trouve, sans relancer l'OCR.
        fichiers._cache.clear()
        assert recherche.rechercher(m, "jardins partagés")["resultats"]
        m.fermer()


def test_langue_et_numero_seul():
    assert ocr.langue_du_texte("La ville est un objet que les sociologues étudient dans la durée.", ["fra", "eng"]) == "fra"
    assert ocr.langue_du_texte("The city is an object that sociologists study in the long run.", ["fra", "eng"]) == "eng"
    assert ocr.langue_du_texte("The city and the state.", ["fra"]) == "fra"
    assert [ocr.numero_seul(t) for t in ("12", "- 12 -", "| 953", "p. 12", "Bloc 2 onc", "2017 Green Studies", "")] \
        == ["12", "12", "953", "", "", "", ""]


def _ocr_complet(d: Path, pages: list[list[str]]) -> dict:
    m = Memoire.ouvrir(d)
    s = m.ajouter_source(Source(type="livre", titre="Scan", champs={"editeur": "E"}))
    m.joindre_fichier(s.id, "scan.pdf", pdf_scanne(d, pages))
    chemin, index = m.chemin_fichier(s), d / recherche.DOSSIER_INDEX
    etat = {"restantes": 1}
    while etat["restantes"]:
        etat = ocr.avancer(chemin, index)
    lu = fichiers.texte_du_fichier(chemin, "", index)
    lu["langue"] = fichiers._lire(chemin, index).get("ocr_langue")
    m.fermer()
    return lu


def test_numero_imprime_retrouve_dans_la_marge():
    """Un article scanné qui commence page 41 : la citation doit porter 41, pas « page 1 du PDF »."""
    if not ocr.outil()["disponible"]:
        return
    corps = ["Les politiques culturelles municipales", "reposent sur des équipements de proximité."]
    with dossier_temporaire() as d:
        lu = _ocr_complet(Path(d), [corps + [""] * 30 + [str(n)] for n in (41, 42, 43)])
        assert lu["numerotation"] == "entetes" and [p["etiquette"] for p in lu["pages"]] == ["41", "42", "43"], lu
        assert lu["langue"] == "fra"
        assert "\n\n\n" not in lu["pages"][0]["texte"]


def test_document_anglais_lu_en_anglais():
    if "eng" not in ocr.outil().get("langues", []):
        return
    with dossier_temporaire() as d:
        lu = _ocr_complet(Path(d), [["The regeneration of industrial wastelands", "is transforming the working class",
                                     "neighbourhoods of the city, and this is the main issue for planners."]])
        assert lu["langue"] == "eng"
        assert "regeneration" in lu["pages"][0]["texte"].casefold()


def test_ocr_refuse_ce_qui_n_est_pas_un_pdf():
    if not ocr.outil()["disponible"]:
        return
    with dossier_temporaire() as d:
        chemin = Path(d) / "notes.docx"
        chemin.write_bytes(b"PK")
        try:
            ocr.avancer(chemin, Path(d))
            raise AssertionError("aurait dû refuser")
        except DonneesInvalides as e:
            assert "PDF" in str(e)


if __name__ == "__main__":
    lancer(globals())
