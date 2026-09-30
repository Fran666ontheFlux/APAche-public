import hashlib
import zipfile
from pathlib import Path

from outils import dossier_temporaire, lancer

from memoire import import_dossiers as idos
from memoire.depot import Memoire
from memoire.modele import DonneesInvalides, Extrait, Source
from test_fichiers import pdf

# Un dossier de mémoire type : deux dossiers d'articles,
# des sous-dossiers, et les dossiers hors périmètre.


def arborescence(d):
    racine = Path(d) / "Mon mémoire"
    fichiers = {
        "Articles à lire/Arrieta 2017 - Rooftop beekeeping.pdf": pdf([["Rooftop beekeeping transformations",
                                                                             "https://doi.org/10.9999/0042098016630507"]]),
        "Articles à lire/Quartier/Morel_2010_verger.pdf": pdf([["Le verger de Jeanne Rivière"]]),
        "Articles LUS/article-final-v3.pdf": pdf([["La mise en récit du jardinage partagé"]],
                                                 infos={"Title": "La mise en récit du jardinage partagé",
                                                        "Author": "Julie Pinel; Elsa Vidal"}),
        "Articles LUS/Mayer compost collectif.pdf": pdf([["Compost collectif"]],
                                                             infos={"Title": "Microsoft Word - Mayer.docx"}),
        "Données/Entretiens/entretien-01.pdf": pdf([["Transcription"]]),
        "TPM/TPM final.pdf": pdf([["Travail préparatoire"]]),
    }
    for relatif, contenu in fichiers.items():
        chemin = racine / relatif
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)
    return racine


def ouvrir_a_cote(d):
    """Le mémoire dans un sous-dossier, à côté du « Mon mémoire » simulé."""
    (Path(d) / "donnees").mkdir()
    return Memoire.ouvrir(Path(d) / "donnees")


def _memoire_avec_onglets(d):
    """Des sources comme les crée l'import du Google Doc : le nom d'onglet, sans fichier."""
    m = ouvrir_a_cote(d)
    for onglet, auteurs, statut in (("Arrieta: Rooftop Beekeeping", [{"nom": "Arrieta", "prenom": ""}], "fiche"),
                                    ("Mayer Compost Coll", [], "a_lire"),
                                    ("Pinel 2017", [{"nom": "Pinel", "prenom": ""}], "a_lire")):
        s = m.ajouter_source(Source(type="article_revue", auteurs=auteurs, titre=onglet, statut=statut,
                                    annee="2017" if onglet == "Pinel 2017" else "",
                                    provenance="import_extraits", origine_import={"onglet": onglet}))
        m.ajouter_extrait(Extrait(source_id=s.id, texte=f"Extrait de {onglet}", nature="paraphrase"))
    return m


def _par_nom(apercu):
    return {f["nom"]: f for f in apercu["fichiers"]}


def test_dossiers_reconnus():
    assert [idos.statut_du_dossier(n) for n in ("Articles à lire", "Articles a lire", "Articles LUS", "Lu",
                                                "Données", "TPM", "Lectures")] == \
        ["a_lire", "a_lire", "lu", "lu", None, None, None]
    with dossier_temporaire() as d:
        trouves, ignores = idos.parcourir(arborescence(d))
    assert sorted(ignores) == ["Données", "TPM"]  # hors périmètre : jamais importés
    assert {f.relatif.replace("\\", "/"): f.statut for f in trouves} == {
        "Articles LUS/Mayer compost collectif.pdf": "lu",
        "Articles LUS/article-final-v3.pdf": "lu",
        "Articles à lire/Arrieta 2017 - Rooftop beekeeping.pdf": "a_lire",
        "Articles à lire/Quartier/Morel_2010_verger.pdf": "a_lire",  # sous-dossier compris
    }


def test_un_seul_des_deux_dossiers_indique_directement():
    with dossier_temporaire() as d:
        trouves, _ = idos.parcourir(arborescence(d) / "Articles LUS")
    assert len(trouves) == 2 and {f.statut for f in trouves} == {"lu"}


def test_dossier_sans_articles():
    with dossier_temporaire() as d:
        for chemin, attendu in ((Path(d) / "absent", "introuvable"), (Path(d), "Aucun dossier")):
            try:
                idos.parcourir(chemin)
                raise AssertionError(chemin)
            except DonneesInvalides as e:
                assert attendu in str(e)


def test_ce_que_le_fichier_dit_de_lui_meme():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        f = _par_nom(idos.apercu(m, arborescence(d)))
        arrieta = f["Arrieta 2017 - Rooftop beekeeping.pdf"]["proposition"]
        assert (arrieta["auteurs"], arrieta["annee"], arrieta["titre"]) == (
            [{"nom": "Arrieta", "prenom": ""}], "2017", "Rooftop beekeeping")
        assert arrieta["doi"] == "https://doi.org/10.9999/0042098016630507"  # lu dans le texte de la 1re page
        pinel = f["article-final-v3.pdf"]["proposition"]  # nom de fichier muet : les métadonnées parlent
        assert pinel["titre"] == "La mise en récit du jardinage partagé"
        assert pinel["auteurs"] == [{"nom": "Pinel", "prenom": "Julie"}, {"nom": "Vidal", "prenom": "Elsa"}]
        # Un titre de métadonnées mis d'office par Word ne vaut rien : le nom du fichier le remplace.
        assert f["Mayer compost collectif.pdf"]["proposition"]["titre"] == "Mayer compost collectif"
        assert "Rooftop" in f["Arrieta 2017 - Rooftop beekeeping.pdf"]["debut"]
        morel = f["Morel_2010_verger.pdf"]["proposition"]
        assert (morel["auteurs"], morel["annee"], morel["titre"]) == ([{"nom": "Morel", "prenom": ""}], "2010",
                                                                         "verger")
        m.fermer()
    with dossier_temporaire() as d:  # « Auteur - Titre », sans année
        racine = Path(d) / "Articles LUS"
        racine.mkdir()
        (racine / "Moretti - On the road.pdf").write_bytes(pdf([["On the road"]]))
        m = ouvrir_a_cote(d)
        [f] = idos.apercu(m, racine)["fichiers"]
        assert (f["proposition"]["auteurs"], f["proposition"]["titre"]) == ([{"nom": "Moretti", "prenom": ""}], "On the road")
        m.fermer()


def test_candidats_parmi_les_sources_sans_fichier():
    with dossier_temporaire() as d:
        m = _memoire_avec_onglets(d)
        f = _par_nom(idos.apercu(m, arborescence(d)))
        etiquettes = lambda nom: [c["etiquette"] for c in f[nom]["candidats"]]
        assert etiquettes("Arrieta 2017 - Rooftop beekeeping.pdf") == ["Arrieta (s. d.)"]
        assert etiquettes("article-final-v3.pdf") == ["Pinel (2017)"]  # par l'auteur des métadonnées
        assert [c["titre"] for c in f["Mayer compost collectif.pdf"]["candidats"]] == ["Mayer Compost Coll"]
        assert etiquettes("Morel_2010_verger.pdf") == []
        m.fermer()


def test_joindre_copie_sans_toucher_l_original_et_ne_se_rejoue_pas():
    with dossier_temporaire() as d:
        m = _memoire_avec_onglets(d)
        racine = arborescence(d)
        original = racine / "Articles LUS" / "article-final-v3.pdf"
        avant = hashlib.sha256(original.read_bytes()).hexdigest()
        pinel = _par_nom(idos.apercu(m, racine))["article-final-v3.pdf"]
        cible = pinel["candidats"][0]["id"]
        idos.appliquer(m, racine, pinel["empreinte"], "joindre", cible)

        s = m.sources[cible]
        assert s.statut == "lu"  # « à lire » dans l'outil, mais rangé dans « Articles LUS »
        assert m.chemin_fichier(s).read_bytes() == original.read_bytes()
        assert original.exists() and hashlib.sha256(original.read_bytes()).hexdigest() == avant  # ni déplacé ni modifié
        assert s.origine_import["onglet"] == "Pinel 2017" and len(m.extraits_de(cible)) == 1

        # Renommé dans le Drive entre deux analyses : reconnu à son contenu.
        original.rename(original.with_name("Pinel Vidal 2017.pdf"))
        relu = _par_nom(idos.apercu(m, racine))["Pinel Vidal 2017.pdf"]
        assert relu["deja"] == {"id": cible} and relu["candidats"] == []
        try:
            idos.appliquer(m, racine, relu["empreinte"], "creer")
            raise AssertionError("aurait dû refuser")
        except DonneesInvalides as e:
            assert "déjà été importé" in str(e)
        m.fermer()


def test_creer_une_source_a_lire():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        racine = arborescence(d)
        arrieta = _par_nom(idos.apercu(m, racine))["Arrieta 2017 - Rooftop beekeeping.pdf"]
        s = m.sources[idos.appliquer(m, racine, arrieta["empreinte"], "creer")["source_id"]]
        assert (s.statut, s.provenance, s.titre, s.annee) == ("a_lire", "depot_fichier", "Rooftop beekeeping", "2017")
        assert s.champs == {"doi": "https://doi.org/10.9999/0042098016630507"}
        assert s.fichier_joint.startswith("fichiers/Arrieta 2017 - Rooftop beekeeping-")
        m.fermer()


def test_statut_jamais_retrograde_et_source_deja_munie():
    with dossier_temporaire() as d:
        m = _memoire_avec_onglets(d)
        racine = arborescence(d)
        f = _par_nom(idos.apercu(m, racine))
        arrieta = f["Arrieta 2017 - Rooftop beekeeping.pdf"]
        cible = arrieta["candidats"][0]["id"]
        idos.appliquer(m, racine, arrieta["empreinte"], "joindre", cible)
        assert m.sources[cible].statut == "fiche"  # rangé « à lire » dans le Drive, mais déjà fiché ici
        morel = f["Morel_2010_verger.pdf"]
        try:
            idos.appliquer(m, racine, morel["empreinte"], "joindre", cible)
            raise AssertionError("une source n'a qu'un fichier")
        except DonneesInvalides as e:
            assert "déjà un fichier" in str(e)
        m.fermer()


def test_fichier_modifie_ou_disparu_depuis_l_analyse():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        racine = arborescence(d)
        f = _par_nom(idos.apercu(m, racine))
        chemin = racine / "Articles à lire" / "Arrieta 2017 - Rooftop beekeeping.pdf"
        chemin.write_bytes(pdf([["Version corrigée"]]))
        for empreinte, attendu in ((f[chemin.name]["empreinte"], "a changé"), ("0" * 20, "plus dans le dossier")):
            try:
                idos.appliquer(m, racine, empreinte, "creer")
                raise AssertionError(attendu)
            except DonneesInvalides as e:
                assert attendu in str(e), e
        assert not m.sources
        m.fermer()


def test_word_accepte():
    with dossier_temporaire() as d:
        racine = Path(d) / "Articles à lire"
        racine.mkdir()
        with zipfile.ZipFile(racine / "notes de lecture.docx", "w") as z:
            z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                       '<w:body><w:p><w:r><w:t>Mes notes.</w:t></w:r></w:p></w:body></w:document>')
        m = ouvrir_a_cote(d)
        [f] = idos.apercu(m, racine)["fichiers"]
        assert f["statut"] == "a_lire" and f["debut"] == "Mes notes."
        m.fermer()


def test_auteurs_des_metadonnees():
    a = idos.auteurs_des_metadonnees
    assert a("Slater, Tom") == [{"nom": "Slater", "prenom": "Tom"}]  # « Nom, Prénom » : une seule personne
    assert a("Van Criekingen, Mathieu") == [{"nom": "Van Criekingen", "prenom": "Mathieu"}]
    assert a("Tom Slater, Loretta Lees") == [{"nom": "Slater", "prenom": "Tom"}, {"nom": "Lees", "prenom": "Loretta"}]
    assert a("Lees, Loretta and Slater, Tom") == [{"nom": "Lees", "prenom": "Loretta"}, {"nom": "Slater", "prenom": "Tom"}]


def test_fichier_refuse_ne_laisse_pas_de_source_vide():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        racine = arborescence(d)
        arrieta = _par_nom(idos.apercu(m, racine))["Arrieta 2017 - Rooftop beekeeping.pdf"]
        chemin = racine / "Articles à lire/Arrieta 2017 - Rooftop beekeeping.pdf"
        chemin.write_bytes(b"pas un pdf")  # abîmé entre l'analyse et l'import
        idos._analyses.clear()
        try:
            idos.appliquer(m, racine, idos._empreinte(chemin), "creer")
            raise AssertionError("aurait dû refuser")
        except DonneesInvalides:
            pass
        assert not m.sources  # aucune source vide créée, rien à dupliquer au prochain essai
        m.fermer()


if __name__ == "__main__":
    lancer(globals())
