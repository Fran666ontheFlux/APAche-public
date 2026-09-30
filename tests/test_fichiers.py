import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote

from outils import dossier_temporaire, lancer

from memoire import fichiers
from memoire.depot import Memoire
from memoire.modele import DonneesInvalides, Source
from test_sources_serveur import avec_client

# PDF fabriqués à la main : quelques lignes de texte par page, en Helvetica,
# pour tester la lecture et la numérotation sans dépendre de vrais articles.


def _chaine_pdf(texte):
    return "(" + texte.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def pdf(pages, premiere_etiquette=None, infos=None):
    """`pages` : liste de listes de lignes (une page sans ligne = page scannée).
    `infos` : métadonnées du PDF, ex. {"Title": "…", "Author": "…"}."""
    objets = {}
    n_pages = len(pages)
    ids_pages = [4 + 2 * i for i in range(n_pages)]
    labels = f" /PageLabels << /Nums [0 << /S /D /St {premiere_etiquette} >>] >>" if premiere_etiquette else ""
    objets[1] = f"<< /Type /Catalog /Pages 2 0 R{labels} >>"
    objets[2] = f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in ids_pages)}] /Count {n_pages} >>"
    objets[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    for i, lignes in enumerate(pages):
        flux = "BT /F1 11 Tf 14 TL 72 760 Td " + " ".join(f"{_chaine_pdf(l)} Tj T*" for l in lignes) + " ET"
        flux = flux.encode("cp1252")
        objets[ids_pages[i]] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {ids_pages[i] + 1} 0 R >>")
        objets[ids_pages[i] + 1] = b"<< /Length %d >>\nstream\n" % len(flux) + flux + b"\nendstream"
    id_infos = max(objets) + 1 if infos else None
    if infos:
        objets[id_infos] = "<< " + " ".join(f"/{cle} {_chaine_pdf(valeur)}" for cle, valeur in infos.items()) + " >>"
    sortie = bytearray(b"%PDF-1.4\n")
    positions = {}
    for num in sorted(objets):
        positions[num] = len(sortie)
        corps = objets[num] if isinstance(objets[num], bytes) else objets[num].encode("cp1252")
        sortie += b"%d 0 obj\n" % num + corps + b"\nendobj\n"
    xref = len(sortie)
    sortie += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
    for num in sorted(objets):
        sortie += b"%010d 00000 n \n" % positions[num]
    lien_infos = b" /Info %d 0 R" % id_infos if infos else b""
    sortie += b"trailer\n<< /Size %d /Root 1 0 R%s >>\nstartxref\n%d\n%%%%EOF\n" % (len(objets) + 1, lien_infos, xref)
    return bytes(sortie)


def ecrire(dossier, nom, contenu):
    chemin = Path(dossier) / nom
    chemin.write_bytes(contenu)
    return chemin


ARTICLE = [  # comme un article de revue : pas de numéro en première page, puis 954, 955 en en-tête
    ["Rooftop beekeeping transformations", "Green Studies 2017, 54(4)", "The first page of the article."],
    ["954", "Green Studies 54(4)", "Artists act as the expeditionary force of greening."],
    ["Arrieta", "The symbolic dimension of consumption.", "955"],
]


# --- Lecture et numérotation ----------------------------------------------------------

def test_numeros_lus_dans_les_entetes():
    with dossier_temporaire() as d:
        lu = fichiers.texte_du_fichier(ecrire(d, "article.pdf", pdf(ARTICLE)))
    assert (lu["type"], lu["numerotation"], lu["scanne"]) == ("pdf", "entetes", False)
    assert [p["etiquette"] for p in lu["pages"]] == ["953", "954", "955"]
    assert "expeditionary force" in lu["pages"][1]["texte"]


def test_pages_avant_la_page_1_sans_numero():
    pages = [["Couverture"], ["Sommaire"], ["Introduction", "1"], ["Suite", "2"], ["Fin", "3"]]
    with dossier_temporaire() as d:
        lu = fichiers.texte_du_fichier(ecrire(d, "guide.pdf", pdf(pages)))
    assert [p["etiquette"] for p in lu["pages"]] == ["", "", "1", "2", "3"]
    assert (lu["premiere"], lu["premiere_pdf"]) == ("1", 3)


def test_annees_et_volumes_ne_font_pas_une_numerotation():
    pages = [["Green Studies 2017, 54(4)", f"Paragraphe {i}."] for i in range(4)]
    with dossier_temporaire() as d:
        lu = fichiers.texte_du_fichier(ecrire(d, "sans.pdf", pdf(pages)))
    assert lu["numerotation"] == "a_verifier"  # rien de sûr : numérotation du PDF, à vérifier
    assert [p["etiquette"] for p in lu["pages"]] == ["1", "2", "3", "4"]


def test_numerotation_inscrite_dans_le_pdf():
    pages = [[f"Texte de la page {i}."] for i in range(3)]
    with dossier_temporaire() as d:
        lu = fichiers.texte_du_fichier(ecrire(d, "etiquettes.pdf", pdf(pages, premiere_etiquette=137)))
    assert lu["numerotation"] == "pdf" and lu["premiere"] == "137"
    assert [p["etiquette"] for p in lu["pages"]] == ["137", "138", "139"]


def test_premiere_page_indiquee_par_l_utilisateur_l_emporte():
    with dossier_temporaire() as d:
        lu = fichiers.texte_du_fichier(ecrire(d, "article.pdf", pdf(ARTICLE)), premiere_page="12")
    assert lu["numerotation"] == "manuelle"
    assert [p["etiquette"] for p in lu["pages"]] == ["12", "13", "14"]


def test_pdf_scanne_signale():
    with dossier_temporaire() as d:
        lu = fichiers.texte_du_fichier(ecrire(d, "scan.pdf", pdf([[], [], []])))
    assert lu["scanne"] and len(lu["pages"]) == 3


def test_texte_d_un_word():
    with dossier_temporaire() as d:
        chemin = Path(d) / "notes.docx"
        with zipfile.ZipFile(chemin, "w") as z:
            z.writestr("word/document.xml",
                       '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                       '<w:p><w:r><w:t>Premier paragraphe.</w:t></w:r></w:p><w:p/>'
                       '<w:p><w:r><w:t>Second paragraphe.</w:t></w:r></w:p></w:body></w:document>')
        lu = fichiers.texte_du_fichier(chemin)
    assert lu["type"] == "docx" and lu["numerotation"] == "aucune"
    assert lu["pages"] == [{"etiquette": "", "texte": "Premier paragraphe.\n\nSecond paragraphe."}]


def test_fichiers_refuses_avec_un_message_clair():
    for nom, contenu, attendu in (("vieux.doc", b"\xd0\xcf\x11\xe0", "enregistre-le au format .docx"),
                                  ("image.png", b"\x89PNG", "ni un PDF ni un Word"),
                                  ("faux.pdf", b"<html>", "n'en est pas un")):
        try:
            fichiers.verifier_fichier(nom, contenu)
            raise AssertionError(nom)
        except DonneesInvalides as e:
            assert attendu in str(e), (nom, e)


# --- Fichier joint à une source ----------------------------------------------------------

def test_joindre_copie_et_remplace():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        s = m.ajouter_source(Source(type="article_revue"))
        m.joindre_fichier(s.id, 'Arrieta: "Culture"?.pdf', pdf(ARTICLE))
        premier = m.chemin_fichier(s)
        assert s.fichier_joint == f"fichiers/Arrieta_ _Culture__-{s.id}.pdf"  # caractères interdits sous Windows remplacés
        assert premier.read_bytes().startswith(b"%PDF")
        m.modifier_source(s.id, premiere_page="953")
        m.joindre_fichier(s.id, "version-corrigee.pdf", pdf(ARTICLE[:1]))
        assert not premier.exists() and m.chemin_fichier(s).name == f"version-corrigee-{s.id}.pdf"
        assert s.premiere_page == ""  # nouveau fichier : la numérotation est à refaire
        m.fermer()
        relu = Memoire.ouvrir(Path(d))
        assert relu.sources[s.id].fichier_joint == f"fichiers/version-corrigee-{s.id}.pdf"
        relu.fermer()


def test_chemin_joint_ne_sort_jamais_du_dossier():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        s = m.ajouter_source(Source(type="livre", fichier_joint="../../Windows/win.ini"))
        assert m.chemin_fichier(s) is None
        m.fermer()


# --- Par le serveur -------------------------------------------------------------------

def envoyer(client, source_id, nom, contenu, type_="application/octet-stream"):
    requete = urllib.request.Request(f"http://127.0.0.1:{client.port}/api/sources/{source_id}/fichier", method="POST",
                                     data=contenu, headers={"Content-Type": type_, "X-Nom-Fichier": quote(nom)})
    try:
        with urllib.request.urlopen(requete) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


@avec_client
def test_deposer_lire_et_rouvrir_par_le_serveur(client):
    _, vue = client("POST", "/api/sources", {"type": "article_revue"})
    id_ = vue["cree"]
    statut, vue = envoyer(client, id_, "Arrieta 2017 é.pdf", pdf(ARTICLE))
    assert statut == 200 and vue["fichier"] == {"nom": "Arrieta 2017 é.pdf", "present": True}

    statut, texte = client("GET", f"/api/sources/{id_}/texte")
    assert statut == 200 and [p["etiquette"] for p in texte["pages"]] == ["953", "954", "955"]
    client("PATCH", f"/api/sources/{id_}", {"premiere_page": "1"})
    _, texte = client("GET", f"/api/sources/{id_}/texte")
    assert texte["numerotation"] == "manuelle" and texte["pages"][2]["etiquette"] == "3"

    with urllib.request.urlopen(f"http://127.0.0.1:{client.port}/api/sources/{id_}/fichier") as r:
        assert r.headers["Content-Type"] == "application/pdf" and r.read() == pdf(ARTICLE)
    _, liste = client("GET", "/api/sources")
    assert liste["sources"][0]["a_fichier"]


@avec_client
def test_depot_refuse_sans_le_bon_type(client):
    _, vue = client("POST", "/api/sources", {"type": "livre"})
    # Un formulaire d'un autre site ne peut envoyer que ces types-là : refusés.
    for type_ in ("text/plain", "multipart/form-data", "application/x-www-form-urlencoded"):
        statut, _ = envoyer(client, vue["cree"], "a.pdf", pdf(ARTICLE), type_)
        assert statut == 415, type_
    statut, erreur = envoyer(client, vue["cree"], "a.doc", b"\xd0\xcf")
    assert statut == 400 and ".docx" in erreur["erreur"]
    statut, erreur = client("GET", f"/api/sources/{vue['cree']}/texte")
    assert statut == 400 and "introuvable" in erreur["erreur"]


if __name__ == "__main__":
    lancer(globals())
