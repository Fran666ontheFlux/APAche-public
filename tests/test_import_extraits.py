import hashlib
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from outils import dossier_temporaire, lancer

from memoire import import_extraits as ie
from memoire.depot import Memoire
from memoire.modele import DonneesInvalides, Extrait, MotCle, Source

# Petits .docx fabriqués à la main, qui reproduisent la structure de l'export
# Word du vrai Google Doc (examiné avant d'écrire l'import) : un titre de style
# « Title » par onglet, une ligne de PDF par paragraphe, du barré, des
# commentaires de marge.

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def onglet(titre):
    return f'<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>{escape(titre)}</w:t></w:r></w:p>'


def para(*morceaux, commentaire=None):
    """Un paragraphe ; chaque morceau est un texte, ou (texte, "barre")."""
    runs = []
    for m in morceaux:
        texte, barre = (m, False) if isinstance(m, str) else (m[0], True)
        rpr = "<w:rPr><w:strike/></w:rPr>" if barre else ""
        runs.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(texte)}</w:t></w:r>')
    if commentaire is not None:
        runs.insert(0, f'<w:commentRangeStart w:id="{commentaire}"/>')
        runs.append(f'<w:commentRangeEnd w:id="{commentaire}"/>')
    return "<w:p>" + "".join(runs) + "</w:p>"


VIDE = "<w:p/>"


def docx(dossier, *paragraphes, commentaires=None, nom="extraits.docx"):
    chemin = Path(dossier) / nom
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("word/document.xml", f'<w:document {W_NS}><w:body>{"".join(paragraphes)}</w:body></w:document>')
        if commentaires:
            corps = "".join(f'<w:comment w:id="{i}"><w:p><w:r><w:t>{escape(t)}</w:t></w:r></w:p></w:comment>'
                            for i, t in commentaires.items())
            z.writestr("word/comments.xml", f'<w:comments {W_NS}>{corps}</w:comments>')
    return chemin


def document_type(d):
    return docx(
        d,
        onglet("PLANNING"), para("Rendre le plan en mars"),
        onglet("Littérature"),
        onglet("Végétalisation"),
        onglet("Martin 2020"),
        para("Les artistes précèdent les promoteurs dans les quartiers en"),
        para("transformation, puis en sont chassés. p12"),
        VIDE,
        para("Idée : comparer avec Bruxelles"),
        onglet("Compost Coll"),
        onglet("Dubois: Les jardins"),
        para(("L'compost collectif est devenue une affaire de voisins.", "barre")),
        onglet("Meeting 12/03"), para("Prochain rendez-vous dans deux semaines"),
    )


def _extraits(*paragraphes):
    with dossier_temporaire() as d:
        lus = ie.analyser(docx(d, onglet("Thème"), onglet("Source"), *paragraphes))
    return lus[0].extraits


# --- Onglets --------------------------------------------------------------------

def test_themes_sources_et_onglets_hors_lecture():
    with dossier_temporaire() as d:
        lus = {o.titre: o for o in ie.analyser(document_type(d))}
    assert set(lus) == {"PLANNING", "Martin 2020", "Dubois: Les jardins", "Meeting 12/03"}
    # « Littérature » est vide et suivi d'un autre onglet vide : un conteneur, pas un thème.
    assert lus["Martin 2020"].theme == "Végétalisation"
    assert lus["Dubois: Les jardins"].theme == "Compost Coll"
    assert lus["Martin 2020"].propose and lus["Dubois: Les jardins"].propose
    assert not lus["PLANNING"].propose        # avant les notes de lecture
    assert not lus["Meeting 12/03"].propose   # après, mais pas une lecture


def test_source_depuis_nom_d_onglet():
    cas = {
        "Pinel 2017": ([{"nom": "Pinel", "prenom": ""}], "2017", ""),
        "Zanetti2022: En Europe": ([{"nom": "Zanetti", "prenom": ""}], "2022", "En Europe"),
        "Arrieta: Rooftop Beekeeping": ([{"nom": "Arrieta", "prenom": ""}], "", "Rooftop Beekeeping"),
        "LUMEN: Socio Po de la rue": ([{"nom": "Lumen", "prenom": ""}], "", "Socio Po de la rue"),
        "Verbeke2021 Patri indu belge": ([{"nom": "Verbeke", "prenom": ""}], "2021", "Patri indu belge"),
        # Plusieurs mots avant les deux-points : on ne devine pas, le nom d'onglet reste le titre.
        "Th.. Pfeiffer B.Reiter: Grands parcs": ([], "", "Th.. Pfeiffer B.Reiter: Grands parcs"),
        "Jardin de la rue Haute": ([], "", "Jardin de la rue Haute"),
    }
    for titre, attendu in cas.items():
        assert ie.source_depuis_onglet(titre) == attendu, titre


# --- Blocs et texte -------------------------------------------------------------

def test_lignes_de_pdf_recollees_en_un_extrait():
    extraits = _extraits(
        para("Ces potagers partagés se multi-"),
        para("plient dans les quartiers depuis la fin des"),
        para("années 1990."),
        VIDE,
        para("Deuxième extrait."))
    assert [e.texte for e in extraits] == [
        "Ces potagers partagés se multiplient dans les quartiers depuis la fin des années 1990.",
        "Deuxième extrait."]


def test_liste_courte_garde_ses_retours_a_la_ligne():
    extraits = _extraits(para("Deux options :"), para("Démolition totale"), para("Réutilisation des bâtiments"))
    assert extraits[0].texte == "Deux options :\nDémolition totale\nRéutilisation des bâtiments"


def test_notations_de_page_en_fin_de_bloc():
    cas = {
        "texte p1": ("1", ""),
        "texte (p14)": ("14", ""),
        "texte p. 12)": ("12", ""),
        "texte (p.18)": ("18", ""),
        "texte pp12-14": ("12", "14"),
        "texte p2-3": ("2", "3"),
        "texte p112-14": ("112", "114"),
        "texte.p8": ("8", ""),
        "texte (p. 12).": ("12", ""),  # point final après la page
        "texte p. 12.": ("12", ""),
        # La page d'un auteur cité par le texte n'est pas celle du texte lu.
        "comme l'écrit Ley (Ley, 2003, p. 12)": ("", ""),
        "comme l'écrit Ley (Ley, 2003, p. 12).": ("", ""),
        "selon eux (Dumas et Guillot, p. 2).": ("", ""),
        "texte sans page": ("", ""),
    }
    for ligne, (debut, fin) in cas.items():
        e = _extraits(para(ligne))[0]
        assert (e.page_debut, e.page_fin) == (debut, fin), ligne
        if debut:  # la page est retirée du texte, la ponctuation reste
            assert e.texte == ("texte." if ligne == "texte.p8" else "texte"), ligne


def test_page_en_debut_de_bloc():
    e = _extraits(para("p13 Les associations coopèrent avec les communes"))[0]
    assert (e.page_debut, e.texte) == ("13", "Les associations coopèrent avec les communes")


def test_page_en_fin_de_ligne_coupe_le_bloc():
    # Ligne vide oubliée après le numéro de page : deux passages, deux extraits.
    extraits = _extraits(para("La tonte est interdite. (p15)"), para("Les serres ferment."), para("p16"))
    assert [(e.texte, e.page_debut) for e in extraits] == [
        ("La tonte est interdite.", "15"), ("Les serres ferment.", "16")]


def test_page_seule_apres_ligne_vide_va_au_bloc_precedent():
    extraits = _extraits(para("Un passage."), VIDE, para("p4"), VIDE, para("Un autre."))
    assert [(e.texte, e.page_debut) for e in extraits] == [("Un passage.", "4"), ("Un autre.", "")]


def test_barre_donne_integre():
    extraits = _extraits(
        para(("Entièrement barré.", "barre")), VIDE,
        para(("Barré en grande partie, ", "barre"), "pas ici."), VIDE,
        para("Presque pas ", ("barré.", "barre")), VIDE,
        para("Pas barré du tout."))
    assert [e.integre for e in extraits] == [True, True, False, False]
    assert [e.barre_en_partie for e in extraits] == [False, True, True, False]


def test_commentaire_couvrant_plusieurs_paragraphes():
    with dossier_temporaire() as d:
        chemin = docx(d, onglet("Thème"), onglet("Source"),
                      '<w:p><w:commentRangeStart w:id="7"/><w:r><w:t>Début</w:t></w:r></w:p>',
                      '<w:p><w:r><w:t>suite</w:t></w:r><w:commentRangeEnd w:id="7"/></w:p>',
                      VIDE, para("Hors commentaire."),
                      commentaires={"7": "Flagship project"})
        extraits = ie.analyser(chemin)[0].extraits
    assert [e.commentaires for e in extraits] == [["Flagship project"], []]


# --- Import dans le mémoire -----------------------------------------------------

def test_import_complet():
    with dossier_temporaire() as d:
        chemin = document_type(d)
        m = Memoire.ouvrir(Path(d))
        rapport = ie.importer(m, chemin)
        assert rapport["sources_creees"] == 2 and rapport["extraits_crees"] == 3
        assert sorted(rapport["mots_cles_crees"]) == ["Compost Coll", "Végétalisation"]

        martin = next(s for s in m.sources.values() if s.origine_import["onglet"] == "Martin 2020")
        assert (martin.auteurs, martin.annee, martin.statut, martin.provenance) == (
            [{"nom": "Martin", "prenom": ""}], "2020", "fiche", "import_extraits")
        idee, citation = sorted(m.extraits_de(martin.id), key=lambda e: e.page_debut)
        assert (citation.nature, citation.page_debut, citation.integre) == ("citation", "12", False)
        assert (idee.nature, idee.page_debut) == ("paraphrase", "")
        végétalisation = next(x for x in m.mots_cles.values() if x.libelle == "Végétalisation")
        assert citation.mots_cles == [végétalisation.id] and végétalisation.couleur

        dubois = next(s for s in m.sources.values() if s.origine_import["onglet"] == "Dubois: Les jardins")
        assert [e.integre for e in m.extraits_de(dubois.id)] == [True]
        # Tout est bien écrit sur le disque, pas seulement en mémoire.
        m.fermer()
        m2 = Memoire.ouvrir(Path(d))
        assert len(m2.extraits) == 3 and len(m2.sources) == 2
        m2.fermer()


def test_import_rejouable_sans_doublon_et_sans_toucher_au_fichier():
    with dossier_temporaire() as d:
        chemin = document_type(d)
        empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()
        m = Memoire.ouvrir(Path(d))
        ie.importer(m, chemin)
        # L'utilisateur renomme un thème et corrige un extrait entre deux imports.
        theme = next(x for x in m.mots_cles.values() if x.libelle == "Compost Coll")
        m.modifier_mot_cle(theme.id, libelle="Compost collectif")
        extrait = next(e for e in m.extraits.values() if e.page_debut == "12")
        m.modifier_extrait(extrait.id, texte="Texte corrigé à la main.")

        rapport = ie.importer(m, chemin)
        assert rapport["sources_creees"] == rapport["extraits_crees"] == 0
        assert rapport["extraits_deja_la"] == 3 and rapport["mots_cles_crees"] == []
        assert len(m.mots_cles) == 2 and len(m.extraits) == 3
        assert m.extraits[extrait.id].texte == "Texte corrigé à la main."
        assert hashlib.sha256(chemin.read_bytes()).hexdigest() == empreinte
        m.fermer()


def test_passage_ajoute_au_google_doc_puis_reimporte():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        ie.importer(m, docx(d, onglet("Thème"), onglet("Martin 2020"), para("Premier.")))
        rapport = ie.importer(m, docx(d, onglet("Thème"), onglet("Martin 2020"), para("Premier."), VIDE,
                                      para("Ajouté depuis."), nom="v2.docx"))
        assert (rapport["sources_creees"], rapport["sources_completees"], rapport["extraits_crees"]) == (0, 1, 1)
        assert len(m.sources) == 1 and len(m.extraits) == 2
        m.fermer()


def test_mot_cle_deja_saisi_reutilise():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        existant = m.ajouter_mot_cle("Jardins", synonymes=["compost coll"])
        ie.importer(m, docx(d, onglet("Compost Coll"), onglet("Martin 2020"), para("Un passage.")))
        assert list(m.mots_cles) == [existant.id]
        assert next(iter(m.extraits.values())).mots_cles == [existant.id]
        m.fermer()


def test_seulement_les_onglets_choisis():
    with dossier_temporaire() as d:
        chemin = document_type(d)
        m = Memoire.ouvrir(Path(d))
        apercu = {o["titre"]: o for o in ie.apercu(m, chemin)["onglets"]}
        assert apercu["Martin 2020"]["propose"] and not apercu["Meeting 12/03"]["propose"]
        assert (apercu["Martin 2020"]["extraits"], apercu["Martin 2020"]["avec_page"]) == (2, 1)
        assert not m.sources  # l'aperçu n'écrit rien
        ie.importer(m, chemin, onglets=["Dubois: Les jardins", "Meeting 12/03"])
        assert sorted(s.origine_import["onglet"] for s in m.sources.values()) == ["Dubois: Les jardins", "Meeting 12/03"]
        apercu = {o["titre"]: o for o in ie.apercu(m, chemin)["onglets"]}
        assert apercu["Dubois: Les jardins"]["deja_importe"] and apercu["Dubois: Les jardins"]["nouveaux"] == 0
        m.fermer()


def test_fichiers_refuses_avec_un_message_clair():
    with dossier_temporaire() as d:
        faux = Path(d) / "notes.docx"
        faux.write_text("pas un document Word", encoding="utf-8")
        for chemin, attendu in ((faux, "Télécharger → Microsoft Word"), (Path(d) / "absent.docx", "introuvable")):
            try:
                ie.analyser(chemin)
                raise AssertionError("aurait dû refuser " + chemin.name)
            except DonneesInvalides as e:
                assert attendu in str(e)
        try:
            ie.analyser(docx(d, para("Pas d'onglet du tout.")))
            raise AssertionError("aurait dû refuser un document sans onglets")
        except DonneesInvalides as e:
            assert "Aucun onglet" in str(e)


def test_ajout_en_lot_incoherent_n_ajoute_rien():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        source = Source(type="livre")
        orphelin = Extrait(source_id=source.id, texte="x", nature="paraphrase", mots_cles=["inexistant"])
        try:
            m.ajouter_en_lot([MotCle(libelle="A")], [source], [orphelin])
            raise AssertionError("aurait dû refuser")
        except DonneesInvalides:
            pass
        assert not m.mots_cles and not m.sources and not m.extraits
        m.fermer()


if __name__ == "__main__":
    lancer(globals())
