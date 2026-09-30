import hashlib
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from outils import dossier_temporaire, lancer

from memoire import apa
from memoire import import_bibliographie as ib
from memoire.depot import Memoire
from memoire.modele import DonneesInvalides, Extrait, Source
from test_apa import BIBLIO_PARTIE_1, R

# Une bibliographie Word typique (références fictives), décrite run par run (texte, italique ?),
# avec les fautes qu'on y trouve souvent : « & », pp., DOI : …, italiques débordants.
BIBLIO_DOCX = [
    ('Bibliographie', None),
    (None, [('Barrault, F. (2017). ', False), ('Tondre ou semer : Quand les bailleurs sociaux ouvrent leurs pelouses pour la gestion partagée des espaces verts', True), ('. Territoires en débat. https://hal.science/hal-00000001 ', False)]),
    (None, [('Lumen. (2017). Pour une histoire sensible des toits. ', False), ('Espaces & Conflits', True), (', ', False), ('105‑106', True), (', 7‑27. https://doi.org/10.9999/lumen.19432 ', False)]),
    (None, [('Morel, L. (2010). Le verger de Jeanne Rivière : Quelle postérité militante ?', False), (' Espaces et territoires', True), (', 140-141(1-2), 177‑191. https://doi.org/10.9999/esp.140.0177 ', False)]),
    (None, [('Hartmann, R., & Keller, C. G. (1984). The quiet craft of greening. ', False), ('Horizons, 31', True), (', 91–111. https://doi.org/10.9999/778358 ', False)]),
    (None, [('Moretti, M. (2017). ', False), ('Au ras du sol : les nouveaux maraîchers et leur rapport au temps', True), ('. Espaces et territoires, 171(4), 73‑89. DOI : 10.9999/esp.171.0073 ', False)]),
    (None, [('Lefort, C., Brunet, R., & Roux, P. (2020). ', False), ('Les bénévoles dans l’entretien collectif des espaces verts : entre rapports de fatigue et invention de nouvelles façons de “tenir”', True), ('. Communication présentée au colloque ATV2020 – Population, temps, territoires, Collège des études territoriales. https://hal.science/hal-00000002 ', False)]),
    (None, [('Arrieta, X. (2017). Rooftop beekeeping transformations beyond the hobby/industry dichotomy. ', False), ('Green Studies, ', True), ('54(4), 953-970. https://doi.org/10.9999/0042098016630507 ', False)]),
    (None, [('Wisniewski, L., Pichon, L., & Soler, J.-P. (2019). Jardiner la ville : promesses et limites ? ', False), ('Le Belvédère, la revue des politiques culturelles, ', True), ('53, 7–10. https://doi.org/10.9999/obs.053.0007 ', False)]),
    (None, [('Harper Ch. (1991), Who Waters the Commons?, ', False), ('Public Administration', True), (', vol. 69, pp. 3-19. ', False)]),
    (None, [('Russo, B. (2013). Mémoire ouvrière et vergers conservatoires sur des terrains issus de l’industrie textile : Regards croisés sur les faubourgs de Roubaix (France) et de Gand (Belgique). ', False), ('GéoRevue, 26', True), ('. https://doi.org/10.9999/geo.13645 ', False)]),
    (None, [('Mayer, I. (2023). Compost collectif. In M.-P. Boucheron & F. Lestrade (Eds.), Petit lexique des jardins, potagers, vergers, ruchers, espaces partagés, lieux nourriciers (pp. xx–xx). Terre & Vent. https://hal.science/hal-00000002 ', False)]),
    (None, [('Pfeiffer, T., & Reiter, B. (2014). Editorial : Les grands parcs publics dans les quartiers ouvriers en mutation : De la pelouse aux jardins de quartier ?', False), (' Géorama, (1). ', True), ('https://doi.org/10.9999/rgeo.12829 ', False)]),
    (None, [("Pinel, J., & Vidal, E. (2017). La mise en récit du jardinage partagé : Quand les talus fleuris sauvages inspirent les services municipaux des espaces verts. ", False), ("Le Belvédère", True), (', ', False), ('50', True), ('(2), 29‑32. https://doi.org/10.9999/obs.050.0029', False)]),
    (None, [('Prades, B. (2013). Calendriers des semis et partage des pelouses à Lille, Namur et Montréal. ', False), ('Loisir et Territoire / Leisure and Place, 36(1),', True), (' 78–93. https://doi.org/10.9999/07053436.2013.805581 ', False)]),
    (None, [('Van Damme, E. (2024). ', False), ('Jardins urbains et économie locale: méthodes et études de cas', True), ('. Université de Liège. Syllabus de cours.', False)]),
    (None, [("Vernier, M. (2019). Faire collectif au potager : La mise en règle des parcelles. Le rôle de la charte de jardinage dans les mutations de l'organisation sociale de l'association Semis Communs. Dans I. Fabbri (dir.),", False), (' Pratiques du collectif : Actes du colloque international, 9-11 mars 2016', True), (' (pp. 29-43). Éditions du Semis.', False)]),
    (None, [('Zanetti, M. (2022). ', False), ("Le jardinage partagé en Europe : état des lieux et perspectives. ", True), ('Nouvelles Ruralités, 19-20.', False)]),
    ('Sources juridiques', None),
    (None, [("Conseil d'État, Section du contentieux administratif. (2022, 13 janvier). ", False), ("Arrêt n° XV-4370 [Règlement-taxe sur les terrasses, Ville de Mons]", True), ('. https://www.example.org/reglements/2022.01.13-RT-252628.pdf ', False)]),
    (None, [('Région wallonne. (2011, 3 mai). ', False), ("Code wallon des jardins communautaires", True), (' [Version consolidée]. eJustice — Service public fédéral Justice. https://www.ejustice.just.fgov.be/eli/decret/2011/05/03/2011A00000/justel ', False)]),
    ('Sitographie', None),
    (None, [('Cities Network. (2026). ', False), ('Open Gardens', True), ('. Initiative européenne pour la biodiversité (EUBI). https://example.org/fr/projet/open-gardens/ ', False)]),
]

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def docx(dossier, lignes, nom="Biblio.docx"):
    corps = []
    for titre, segments in lignes:
        if titre is not None:
            corps.append(f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{escape(titre)}</w:t></w:r></w:p>')
            continue
        runs = "".join(f'<w:r>{"<w:rPr><w:i/></w:rPr>" if italique else ""}<w:t xml:space="preserve">{escape(t)}</w:t></w:r>'
                       for t, italique in segments)
        corps.append(f"<w:p>{runs}</w:p><w:p/>")
    chemin = Path(dossier) / nom
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("word/document.xml", f'<w:document {W_NS}><w:body>{"".join(corps)}</w:body></w:document>')
    return chemin


def test_lecture_sections_et_italique():
    with dossier_temporaire() as d:
        refs = ib.lire_references(docx(d, BIBLIO_DOCX))
    assert len(refs) == 20
    assert [r.section for r in refs].count("Sources juridiques") == 2 and refs[-1].section == "Sitographie"
    assert refs[1].html.startswith("Lumen. (2017). Pour une histoire sensible des toits. <i>Espaces &amp; Conflits</i>")


def test_decoupage_des_vingt_references():
    # Mesure contre les références validées par l'utilisateur (test_apa) :
    # type et HTML identiques pour 18 sur 20. Les deux autres ne peuvent pas
    # être devinées depuis le fichier, et le signalent.
    with dossier_temporaire() as d:
        refs = ib.lire_references(docx(d, BIBLIO_DOCX))
    ecarts = {}
    for ref, (valide, _) in zip(refs, BIBLIO_PARTIE_1):
        p = ib.analyser(ref)
        if p.type != valide.type or apa.reference(p.source(), R).html != apa.reference(valide, R).html:
            ecarts[valide.auteurs[0].get("nom")] = p.a_verifier
    assert ecarts == {
        # Titre en italique dans le fichier : pris pour une page web, validé comme article de revue.
        "Barrault": ["Type deviné (page web) : vérifie-le."],
        # L'adresse était celle de Lefort et al. ; l'utilisateur l'a retirée à la validation.
        "Mayer": ["Pages « xx–xx » ignorées : ce ne sont pas des numéros."],
    }


def test_auteurs():
    assert ib.auteurs_depuis("Hartmann, R., & Keller, C. G.") == [{"nom": "Hartmann", "prenom": "R."}, {"nom": "Keller", "prenom": "C. G."}]
    assert ib.auteurs_depuis("Wisniewski, L., Pichon, L. et Soler, J.-P.")[2] == {"nom": "Soler", "prenom": "J.-P."}
    assert ib.auteurs_depuis("Harper Ch.") == [{"nom": "Harper", "prenom": "Ch."}]
    assert ib.auteurs_depuis("Van Damme, E.") == [{"nom": "Van Damme", "prenom": "E."}]
    assert ib.auteurs_depuis("Lumen.") == [{"organisation": "Lumen"}]
    assert ib.auteurs_depuis("Conseil d'État, Section du contentieux administratif.") == \
        [{"organisation": "Conseil d'État, Section du contentieux administratif"}]
    assert ib.auteurs_depuis("Ministère de la Culture et de la Communication.") == \
        [{"organisation": "Ministère de la Culture et de la Communication"}]


def _memoire_avec_onglets(d):
    """Des sources telles que l'import du Google Doc les crée : le nom d'onglet, et c'est tout."""
    m = Memoire.ouvrir(Path(d))
    for onglet, auteurs, annee in (("Pinel 2017", [{"nom": "Pinel", "prenom": ""}], "2017"),
                                   ("VIDA Talus et pol urb", [], ""),
                                   ("Hartmann: Quiet craft of végétalisation", [{"nom": "Hartmann", "prenom": ""}], ""),
                                   ("Th.. Pfeiffer B.Reiter: Grands parcs publiqes", [], ""),
                                   ("Lefort 2019", [{"nom": "Lefort", "prenom": ""}], "2019")):
        s = m.ajouter_source(Source(type="article_revue", auteurs=auteurs, annee=annee, titre=onglet, statut="fiche",
                                    provenance="import_extraits", origine_import={"onglet": onglet}))
        m.ajouter_extrait(Extrait(source_id=s.id, texte=f"Extrait de {onglet}", nature="paraphrase"))
    return m


def _par_debut(apercu):
    return {r["reference"]["texte"].split(" (")[0]: r for r in apercu["references"]}


def test_candidats_proposes():
    with dossier_temporaire() as d:
        m = _memoire_avec_onglets(d)
        refs = _par_debut(ib.apercu(m, docx(d, BIBLIO_DOCX)))
        onglets = lambda cle: [c["onglet"] for c in refs[cle]["candidats"]]
        # Le bon d'abord ; l'autre texte de Vidal est proposé aussi, l'utilisateur tranche.
        assert onglets("Pinel, J. et Vidal, E.") == ["Pinel 2017", "VIDA Talus et pol urb"]
        assert onglets("Hartmann, R. et Keller, C. G.") == ["Hartmann: Quiet craft of végétalisation"]  # faute de frappe tolérée
        assert onglets("Pfeiffer, T. et Reiter, B.") == ["Th.. Pfeiffer B.Reiter: Grands parcs publiqes"]  # nom dans l'onglet
        assert onglets("Lefort, C., Brunet, R. et Roux, P.") == []  # 2019 ≠ 2020 : pas la même source
        assert onglets("Morel, L.") == []
        assert refs["Pinel, J. et Vidal, E."]["candidats"][0]["nb_extraits"] == 1
        m.fermer()


def test_fusion_garde_les_extraits_et_ne_se_rejoue_pas():
    with dossier_temporaire() as d:
        m = _memoire_avec_onglets(d)
        chemin = docx(d, BIBLIO_DOCX)
        pinel = _par_debut(ib.apercu(m, chemin))["Pinel, J. et Vidal, E."]
        cible = pinel["candidats"][0]["id"]
        ib.appliquer(m, chemin, pinel["empreinte"], "fusionner", cible)
        s = m.sources[cible]
        assert (s.titre, s.annee, s.citee_partie1, s.champs["revue"]) == (
            "La mise en récit du jardinage partagé : Quand les talus fleuris sauvages inspirent les "
            "services municipaux des espaces verts", "2017", True, "Le Belvédère")
        assert s.origine_import["onglet"] == "Pinel 2017"  # l'import des extraits la retrouve toujours
        assert len(m.extraits_de(cible)) == 1 and s.statut == "fiche"
        relu = next(r for r in ib.apercu(m, chemin)["references"] if r["empreinte"] == pinel["empreinte"])
        assert relu["deja"] == {"id": cible} and relu["candidats"] == []
        try:
            ib.appliquer(m, chemin, pinel["empreinte"], "creer")
            raise AssertionError("aurait dû refuser un second import")
        except DonneesInvalides as e:
            assert "déjà été importée" in str(e)
        # Une source déjà rapprochée n'est plus proposée pour une autre référence.
        assert cible not in [c["id"] for r in ib.apercu(m, chemin)["references"] for c in r["candidats"]]
        # Relu depuis le disque : la fusion est bien enregistrée.
        m.fermer()
        m2 = Memoire.ouvrir(Path(d))
        assert m2.sources[cible].origine_import["reference_biblio"] == pinel["empreinte"]
        m2.fermer()


def test_creation_d_une_nouvelle_source():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        chemin = docx(d, BIBLIO_DOCX)
        empreinte_avant = hashlib.sha256(chemin.read_bytes()).hexdigest()
        cobat = _par_debut(ib.apercu(m, chemin))["Région wallonne."]
        assert cobat["proposition"]["type"] == "texte_legal"
        s = m.sources[ib.appliquer(m, chemin, cobat["empreinte"], "creer")["source_id"]]
        assert (s.provenance, s.statut, s.citee_partie1) == ("import_bibliographie", "lu", True)
        assert apa.reference(s, R).texte == BIBLIO_PARTIE_1[18][1]
        assert hashlib.sha256(chemin.read_bytes()).hexdigest() == empreinte_avant
        m.fermer()


def test_reference_disparue_ou_action_inconnue():
    with dossier_temporaire() as d:
        m = Memoire.ouvrir(Path(d))
        chemin = docx(d, BIBLIO_DOCX)
        for empreinte, action, attendu in (("0" * 16, "creer", "plus dans le fichier"),
                                           (ib.lire_references(chemin)[0].empreinte, "effacer", "Action inconnue")):
            try:
                ib.appliquer(m, chemin, empreinte, action)
                raise AssertionError(action)
            except DonneesInvalides as e:
                assert attendu in str(e)
        assert not m.sources
        m.fermer()


def test_lettre_de_l_annee_non_stockee():
    """« (2020a) » : l'outil recalcule lui-même les lettres ; l'année stockée est 2020."""
    ref = ib.ReferenceLue([("Dupont, J. (2020a). ", False), ("Les jardins", True), (". PUF.", False)])
    prop = ib.analyser(ref)
    assert prop.annee == "2020" and prop.titre == "Les jardins"


if __name__ == "__main__":
    lancer(globals())
