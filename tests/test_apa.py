from outils import lancer

from memoire import apa
from memoire.modele import ReglagesAPA, Source

R = ReglagesAPA()


def p(nom, prenom=""):
    return {"nom": nom, "prenom": prenom}


def org(nom):
    return {"organisation": nom}


def ref(source, reglages=R, suffixe=""):
    return apa.reference(source, reglages, suffixe).texte


# --- 1. Exemples du guide ULB (V10, 05/02/2024) ------------------------------------
# Recopiés du guide, sauf ses coquilles évidentes (espaces, point manquant).
# Écarts voulus, validés par l'utilisateur : « et » sans virgule avant (modèle
# du guide ; son exemple Winston en met une), 1re édition omise,
# « (dir.) » en français là où l'exemple anglais du guide écrit « (Eds.) ».

def test_guide_ulb_article():
    s = Source(type="article_revue", auteurs=[p("Winston", "G. W."), p("Di Giulio", "R. T.")], annee="1991",
               titre="Prooxidant and antioxidant mechanisms in aquatic organisms",
               champs={"revue": "Aquatic Toxicology", "volume": "19", "numero": "2", "pages": "137-161",
                       "doi": "https://doi.org/10.1016/0166-445X(91)90033-6"})
    assert ref(s) == ("Winston, G. W. et Di Giulio, R. T. (1991). Prooxidant and antioxidant mechanisms in aquatic "
                      "organisms. Aquatic Toxicology, 19(2), 137-161. https://doi.org/10.1016/0166-445X(91)90033-6")
    assert apa.reference(s, R).html.startswith("Winston") and "<i>Aquatic Toxicology, 19</i>(2)" in apa.reference(s, R).html


def test_guide_ulb_livre():
    s = Source(type="livre", auteurs=[p("Verchier", "Y."), p("Gerber", "N.")], annee="2011",
               titre="Vous avez dit chimie? : De la cuisine au salon, des molécules plein la maison",
               champs={"volume": "1", "editeur": "Dunod"})
    assert ref(s) == ("Verchier, Y. et Gerber, N. (2011). Vous avez dit chimie? : De la cuisine au salon, "
                      "des molécules plein la maison (vol. 1). Dunod.")
    assert apa.reference(s, R).segments[1][1]  # titre en italique


def test_guide_ulb_these():
    s = Source(type="memoire_these", auteurs=[p("Lehue", "M.")], annee="2019",
               titre="Exploitation collective des ressources chez la fourmi Myrmica rubra : rôle et influence de "
                     "l'interface entre le nid et l'environnement",
               champs={"nature": "Thèse de doctorat", "institution": "Université libre de Bruxelles"})
    assert ref(s) == ("Lehue, M. (2019). Exploitation collective des ressources chez la fourmi Myrmica rubra : rôle "
                      "et influence de l'interface entre le nid et l'environnement [Thèse de doctorat]. "
                      "Université libre de Bruxelles.")


def test_guide_ulb_chapitre():
    s = Source(type="chapitre", auteurs=[p("Williamson", "A."), p("Hillier", "W."), p("Wydrzynskli", "T.")],
               annee="2008", titre="Expression of the manganese stabilising protein from a primitive cyanobacterium",
               champs={"directeurs": [p("Allen", "J. F."), p("Gantt", "E."), p("Golbeck", "J. H."), p("Osmond", "B.")],
                       "titre_ouvrage": "Photosynthesis. Energy from the sun", "pages": "525-528",
                       "editeur": "Springer Netherlands"})
    assert ref(s) == ("Williamson, A., Hillier, W. et Wydrzynskli, T. (2008). Expression of the manganese stabilising "
                      "protein from a primitive cyanobacterium. Dans J. F. Allen, E. Gantt, J. H. Golbeck et B. Osmond "
                      "(dir.), Photosynthesis. Energy from the sun (p. 525-528). Springer Netherlands.")


def test_guide_ulb_pages_web():
    herbet = Source(type="page_web", auteurs=[p("Herbet", "M.")], annee="2019",
                    titre="Revues en open access : Les bibliothécaires plus concernés que jamais ?",
                    champs={"date_precise": "20 mai", "site": "Hypothèses", "url": "https://dlis.hypotheses.org/4508"})
    assert ref(herbet) == ("Herbet, M. (2019, 20 mai). Revues en open access : Les bibliothécaires plus concernés "
                           "que jamais ? Hypothèses. https://dlis.hypotheses.org/4508")
    # Le Guide du Master exige la date de consultation : signalée tant qu'elle manque.
    assert apa.reference(herbet, R).manques == ["Consulté le (ex. 29 septembre 2026)"]
    herbet.champs["consulte_le"] = "29 septembre 2026"
    assert ref(herbet).endswith("Hypothèses. Consulté le 29 septembre 2026 de https://dlis.hypotheses.org/4508")

    nobel = Source(type="page_web", auteurs=[org("The Nobel prize")], annee="2024", titre="Nobel prize conversations",
                   champs={"date_precise": "25 janvier", "site": "The Nobel Prize",
                           "url": "https://www.nobelprize.org/nobel-prize-conversations/"})
    assert ref(nobel) == ("The Nobel prize. (2024, 25 janvier). Nobel prize conversations. The Nobel Prize. "
                          "https://www.nobelprize.org/nobel-prize-conversations/")


def test_guide_ulb_citations_dans_le_texte():
    loriau = Source(type="livre", auteurs=[p("Loriau")], annee="2012")
    deux = Source(type="livre", auteurs=[p("Loriau"), p("Cochez")], annee="2011")
    trois = Source(type="livre", auteurs=[p("Masy"), p("Wartin"), p("Merner")], annee="2008")
    assert apa.citation(loriau, R).texte == "(Loriau, 2012)"
    assert apa.citation(loriau, R, narrative=True).texte == "Loriau (2012)"
    assert apa.citation(deux, R).texte == "(Loriau et Cochez, 2011)"
    assert apa.citation(deux, R, narrative=True).texte == "Loriau et Cochez (2011)"
    assert apa.citation(trois, R, narrative=True).texte == "Masy et al. (2008)"
    assert apa.citation(Source(type="livre", auteurs=[p("Loriau")], annee="1999"), R, suffixe="a",
                        narrative=True).texte == "Loriau (1999a)"
    assert apa.citation(Source(type="livre", auteurs=[p("Sadin")], annee="2011"), R,
                        page_debut="14").texte == "(Sadin, 2011, p. 14)"
    # Le guide ULB écrit « in » : réglable dans le projet.
    faway = Source(type="livre", auteurs=[p("Faway")], annee="1999")
    simon = {"auteurs": [p("Simon")], "annee": "1977"}
    assert apa.citation(faway, ReglagesAPA(cite_dans="in"), auteur_origine=simon).texte == "(Simon, 1977, in Faway, 1999)"


# --- 2. Une bibliographie d'exemple (références fictives) ------------------------
# Des références inventées, avec les cas que l'on rencontre en vrai ; le résultat
# attendu est la forme APA corrigée (italiques, DOI, « et »).

BIBLIO_PARTIE_1 = [
    (Source(type="article_revue", auteurs=[p("Barrault", "F.")], annee="2017",
            titre="Tondre ou semer : Quand les bailleurs sociaux ouvrent leurs pelouses pour la gestion "
                  "partagée des espaces verts",
            champs={"revue": "Territoires en débat", "url": "https://hal.science/hal-00000001"}),
     "Barrault, F. (2017). Tondre ou semer : Quand les bailleurs sociaux ouvrent leurs pelouses pour la "
     "gestion partagée des espaces verts. Territoires en débat. https://hal.science/hal-00000001"),
    (Source(type="article_revue", auteurs=[org("Lumen")], annee="2017",
            titre="Pour une histoire sensible des toits",
            champs={"revue": "Espaces & Conflits", "volume": "105‑106", "pages": "7‑27",
                    "doi": "https://doi.org/10.9999/lumen.19432"}),
     "Lumen. (2017). Pour une histoire sensible des toits. Espaces & Conflits, 105-106, 7-27. "
     "https://doi.org/10.9999/lumen.19432"),
    (Source(type="article_revue", auteurs=[p("Morel", "L.")], annee="2010",
            titre="Le verger de Jeanne Rivière : Quelle postérité militante ?",
            champs={"revue": "Espaces et territoires", "volume": "140-141", "numero": "1-2", "pages": "177‑191",
                    "doi": "https://doi.org/10.9999/esp.140.0177"}),
     "Morel, L. (2010). Le verger de Jeanne Rivière : Quelle postérité militante ? "
     "Espaces et territoires, 140-141(1-2), 177-191. https://doi.org/10.9999/esp.140.0177"),
    (Source(type="article_revue", auteurs=[p("Hartmann", "R."), p("Keller", "C. G.")], annee="1984",
            titre="The quiet craft of greening",
            champs={"revue": "Horizons", "volume": "31", "pages": "91–111", "doi": "https://doi.org/10.9999/778358"}),
     "Hartmann, R. et Keller, C. G. (1984). The quiet craft of greening. Horizons, 31, 91-111. "
     "https://doi.org/10.9999/778358"),
    (Source(type="article_revue", auteurs=[p("Moretti", "M.")], annee="2017",
            titre="Au ras du sol : les nouveaux maraîchers et leur rapport au temps",
            champs={"revue": "Espaces et territoires", "volume": "171", "numero": "4", "pages": "73‑89",
                    "doi": "DOI : 10.9999/esp.171.0073"}),
     "Moretti, M. (2017). Au ras du sol : les nouveaux maraîchers et leur rapport au temps. Espaces et territoires, "
     "171(4), 73-89. https://doi.org/10.9999/esp.171.0073"),
    (Source(type="communication_colloque", auteurs=[p("Lefort", "C."), p("Brunet", "R."), p("Roux", "P.")],
            annee="2020",
            titre="Les bénévoles dans l’entretien collectif des espaces verts : entre rapports de "
                  "fatigue et invention de nouvelles façons de “tenir”",
            champs={"evenement": "Colloque ATV2020 – Population, temps, territoires",
                    "lieu": "Collège des études territoriales",
                    "url": "https://hal.science/hal-00000002"}),
     "Lefort, C., Brunet, R. et Roux, P. (2020). Les bénévoles dans l’entretien collectif des "
     "espaces verts : entre rapports de fatigue et invention de nouvelles façons de “tenir” [Communication]. "
     "Colloque ATV2020 – Population, temps, territoires, Collège des études territoriales. "
     "https://hal.science/hal-00000002"),
    (Source(type="article_revue", auteurs=[p("Arrieta", "X.")], annee="2017",
            titre="Rooftop beekeeping transformations beyond the hobby/industry dichotomy",
            champs={"revue": "Green Studies", "volume": "54", "numero": "4", "pages": "953-970",
                    "doi": "https://doi.org/10.9999/0042098016630507"}),
     "Arrieta, X. (2017). Rooftop beekeeping transformations beyond the hobby/industry "
     "dichotomy. Green Studies, 54(4), 953-970. https://doi.org/10.9999/0042098016630507"),
    (Source(type="article_revue", auteurs=[p("Wisniewski", "L."), p("Pichon", "L."), p("Soler", "J.-P.")],
            annee="2019", titre="Jardiner la ville : promesses et limites ?",
            champs={"revue": "Le Belvédère, la revue des politiques culturelles", "volume": "53", "pages": "7–10",
                    "doi": "https://doi.org/10.9999/obs.053.0007"}),
     "Wisniewski, L., Pichon, L. et Soler, J.-P. (2019). Jardiner la ville : promesses et limites ? "
     "Le Belvédère, la revue des politiques culturelles, 53, 7-10. https://doi.org/10.9999/obs.053.0007"),
    (Source(type="article_revue", auteurs=[p("Harper", "Ch.")], annee="1991",
            titre="Who Waters the Commons?",
            champs={"revue": "Public Administration", "volume": "69", "pages": "3-19"}),
     "Harper, Ch. (1991). Who Waters the Commons? Public Administration, 69, 3-19."),
    (Source(type="article_revue", auteurs=[p("Russo", "B.")], annee="2013",
            titre="Mémoire ouvrière et vergers conservatoires sur des terrains issus de l’industrie textile : Regards "
                  "croisés sur les faubourgs de Roubaix (France) et de Gand "
                  "(Belgique)",
            champs={"revue": "GéoRevue", "volume": "26", "doi": "https://doi.org/10.9999/geo.13645"}),
     "Russo, B. (2013). Mémoire ouvrière et vergers conservatoires sur des terrains issus de l’industrie textile : "
     "Regards croisés sur les faubourgs de Roubaix (France) et de Gand "
     "(Belgique). GéoRevue, 26. https://doi.org/10.9999/geo.13645"),
    (Source(type="chapitre", auteurs=[p("Mayer", "I.")], annee="2023", titre="Compost collectif",
            champs={"directeurs": [p("Boucheron", "M.-P."), p("Lestrade", "F.")],
                    "titre_ouvrage": "Petit lexique des jardins, potagers, vergers, ruchers, espaces "
                                     "partagés, lieux nourriciers",
                    "editeur": "Terre & Vent"}),
     "Mayer, I. (2023). Compost collectif. Dans M.-P. Boucheron et F. Lestrade (dir.), Petit lexique des "
     "jardins, potagers, vergers, ruchers, espaces partagés, lieux nourriciers. Terre & Vent."),
    (Source(type="article_revue", auteurs=[p("Pfeiffer", "T."), p("Reiter", "B.")], annee="2014",
            titre="Editorial : Les grands parcs publics dans les quartiers ouvriers en mutation : De la "
                  "pelouse aux jardins de quartier ?",
            champs={"revue": "Géorama", "numero": "1", "doi": "https://doi.org/10.9999/rgeo.12829"}),
     "Pfeiffer, T. et Reiter, B. (2014). Editorial : Les grands parcs publics dans les quartiers ouvriers "
     "en mutation : De la pelouse aux jardins de quartier ? Géorama, (1). "
     "https://doi.org/10.9999/rgeo.12829"),
    (Source(type="article_revue", auteurs=[p("Pinel", "J."), p("Vidal", "E.")], annee="2017",
            titre="La mise en récit du jardinage partagé : Quand les talus fleuris sauvages inspirent les "
                  "services municipaux des espaces verts",
            champs={"revue": "Le Belvédère", "volume": "50", "numero": "2", "pages": "29‑32",
                    "doi": "https://doi.org/10.9999/obs.050.0029"}),
     "Pinel, J. et Vidal, E. (2017). La mise en récit du jardinage partagé : Quand les talus fleuris "
     "sauvages inspirent les services municipaux des espaces verts. Le Belvédère, 50(2), 29-32. "
     "https://doi.org/10.9999/obs.050.0029"),
    (Source(type="article_revue", auteurs=[p("Prades", "B.")], annee="2013",
            titre="Calendriers des semis et partage des pelouses à Lille, Namur et Montréal",
            champs={"revue": "Loisir et Territoire / Leisure and Place", "volume": "36", "numero": "1",
                    "pages": "78–93", "doi": "https://doi.org/10.9999/07053436.2013.805581"}),
     "Prades, B. (2013). Calendriers des semis et partage des pelouses à Lille, Namur et Montréal. "
     "Loisir et Territoire / Leisure and Place, 36(1), 78-93. https://doi.org/10.9999/07053436.2013.805581"),
    (Source(type="support_cours", auteurs=[p("Van Damme", "E.")], annee="2024",
            titre="Jardins urbains et économie locale: méthodes et études de cas",
            champs={"nature": "Syllabus", "institution": "Université de Liège"}),
     "Van Damme, E. (2024). Jardins urbains et économie locale: méthodes et études de cas "
     "[Syllabus]. Université de Liège."),
    (Source(type="chapitre", auteurs=[p("Vernier", "M.")], annee="2019",
            titre="Faire collectif au potager : La mise en règle des parcelles. Le rôle de la charte "
                  "de jardinage dans les mutations de l'organisation sociale de l'association Semis Communs",
            champs={"directeurs": [p("Fabbri", "I.")],
                    "titre_ouvrage": "Pratiques du collectif : Actes du colloque international, 9-11 mars 2016",
                    "pages": "29-43", "editeur": "Éditions du Semis"}),
     "Vernier, M. (2019). Faire collectif au potager : La mise en règle des parcelles. Le rôle de la "
     "charte de jardinage dans les mutations de l'organisation sociale de l'association Semis Communs. "
     "Dans I. Fabbri (dir.), Pratiques du collectif : Actes du colloque international, 9-11 mars 2016 (p. 29-43). "
     "Éditions du Semis."),
    (Source(type="article_revue", auteurs=[p("Zanetti", "M.")], annee="2022",
            titre="Le jardinage partagé en Europe : état des lieux et perspectives",
            champs={"revue": "Nouvelles Ruralités", "volume": "19-20"}),
     "Zanetti, M. (2022). Le jardinage partagé en Europe : état des lieux et perspectives. "
     "Nouvelles Ruralités, 19-20."),
    (Source(type="jurisprudence", auteurs=[org("Conseil d'État, Section du contentieux administratif")], annee="2022",
            titre="Arrêt n° XV-4370",
            champs={"date_precise": "13 janvier",
                    "precision": "Règlement-taxe sur les terrasses, Ville de Mons",
                    "url": "https://www.example.org/reglements/2022.01.13-RT-252628.pdf"}),
     "Conseil d'État, Section du contentieux administratif. (2022, 13 janvier). Arrêt n° XV-4370 [Règlement-taxe "
     "sur les terrasses, Ville de Mons]. "
     "https://www.example.org/reglements/2022.01.13-RT-252628.pdf"),
    (Source(type="texte_legal", auteurs=[org("Région wallonne")], annee="2011",
            titre="Code wallon des jardins communautaires",
            champs={"date_precise": "3 mai", "precision": "Version consolidée",
                    "publication": "eJustice — Service public fédéral Justice",
                    "url": "https://www.ejustice.just.fgov.be/eli/decret/2011/05/03/2011A00000/justel"}),
     "Région wallonne. (2011, 3 mai). Code wallon des jardins communautaires [Version "
     "consolidée]. eJustice — Service public fédéral Justice. "
     "https://www.ejustice.just.fgov.be/eli/decret/2011/05/03/2011A00000/justel"),
    (Source(type="page_web", auteurs=[org("Cities Network")], annee="2026", titre="Open Gardens",
            champs={"site": "Initiative européenne pour la biodiversité (EUBI)",
                    "url": "https://example.org/fr/projet/open-gardens/"}),
     "Cities Network. (2026). Open Gardens. Initiative européenne pour la biodiversité (EUBI). "
     "https://example.org/fr/projet/open-gardens/"),
]


def test_bibliographie_premiere_partie():
    for source, attendu in BIBLIO_PARTIE_1:
        assert ref(source) == attendu, f"\nobtenu : {ref(source)}\nattendu: {attendu}"


def test_italiques_de_la_premiere_partie():
    italiques = {s.auteurs[0].get("nom") or s.auteurs[0].get("organisation"):
                 [t for t, i in apa.reference(s, R).segments if i] for s, _ in BIBLIO_PARTIE_1}
    assert italiques["Lumen"] == ["Espaces & Conflits, 105-106"]  # revue et volume, pas le titre
    assert italiques["Pfeiffer"] == ["Géorama"]
    assert italiques["Van Damme"] == ["Jardins urbains et économie locale: méthodes et études de cas"]
    assert italiques["Mayer"] == ["Petit lexique des jardins, potagers, vergers, ruchers, espaces "
                                   "partagés, lieux nourriciers"]
    # Le crochet d'une description n'est pas en italique.
    assert italiques["Conseil d'État, Section du contentieux administratif"] == ["Arrêt n° XV-4370"]
    lumen = apa.reference(BIBLIO_PARTIE_1[1][0], R).html
    assert "<i>Espaces &amp; Conflits, 105-106</i>, 7-27." in lumen


def test_champs_manquants_signales():
    manques = {s.auteurs[0].get("nom") or s.auteurs[0].get("organisation"): apa.reference(s, R).manques
               for s, _ in BIBLIO_PARTIE_1}
    assert manques["Mayer"] == ["Pages du chapitre (ex. 29-43)"]
    assert manques["Cities Network"] == ["Consulté le (ex. 29 septembre 2026)"]
    assert sum(bool(m) for m in manques.values()) == 2


# --- 3. Règles ---------------------------------------------------------------------

def test_sans_date_et_lettres():
    a = Source(type="livre", auteurs=[p("Martin", "A.")], titre="Bêta", champs={"editeur": "Seuil"})
    b = Source(type="livre", auteurs=[p("Martin", "A.")], titre="Alpha", champs={"editeur": "Seuil"})
    c = Source(type="livre", auteurs=[p("Martin", "A.")], annee="2020", titre="Gamma", champs={"editeur": "Seuil"})
    lettres = apa.suffixes([a, b, c])
    assert lettres == {b.id: "a", a.id: "b"}  # ordre alphabétique des titres ; 2020 seule : pas de lettre
    assert apa.citation(b, R, suffixe="a").texte == "(Martin, s. d.-a)"
    assert ref(b, suffixe="a").startswith("Martin, A. (s. d.-a). Alpha.")


def test_esperluette():
    r = ReglagesAPA(conjonction="&")
    s = BIBLIO_PARTIE_1[3][0]  # Hartmann et Keller
    assert ref(s, r).startswith("Hartmann, R., & Keller, C. G. (1984).")
    assert apa.citation(s, r).texte == "(Hartmann & Keller, 1984)"
    assert apa.citation(s, r, narrative=True).texte == "Hartmann et Keller (1984)"


def test_plus_de_vingt_auteurs():
    s = Source(type="article_revue", auteurs=[p(f"Auteur{i}", "A.") for i in range(1, 23)], annee="2020", titre="T",
               champs={"revue": "R"})
    debut = ref(s).split(" (2020)")[0]
    assert debut.startswith("Auteur1, A., Auteur2, A.,") and ", Auteur19, A., . . . Auteur22, A." in debut
    assert "Auteur20" not in debut
    assert apa.citation(s, R).texte == "(Auteur1 et al., 2020)"


def test_pages_source_secondaire_et_citation_litterale():
    martin = Source(type="livre", auteurs=[p("Martin", "A.")], annee="2020")
    assert apa.citation(martin, R, page_debut="45", page_fin="47").texte == "(Martin, 2020, p. 45-47)"
    assert apa.citation(martin, ReglagesAPA(pages="pp."), page_debut="45", page_fin="47").texte == "(Martin, 2020, pp. 45-47)"
    piaget = {"auteurs": [p("Piaget")], "annee": "1952"}
    assert apa.citation(martin, R, page_debut="45", auteur_origine=piaget).texte == \
        "(Piaget, 1952, cité dans Martin, 2020, p. 45)"
    assert apa.citation(martin, R, page_debut="45", auteur_origine=piaget, narrative=True).texte == \
        "Piaget (1952, cité dans Martin, 2020, p. 45)"
    assert apa.citation_litterale("“La culture pour tous.”", martin, R, page_debut="45").texte == \
        "« La culture pour tous. » (Martin, 2020, p. 45)"


def test_organisation_et_sans_auteur():
    unesco = Source(type="rapport", auteurs=[org("UNESCO")], annee="2022", titre="Re|penser les politiques culturelles",
                    champs={"editeur": "UNESCO"})
    assert apa.citation(unesco, R).texte == "(UNESCO, 2022)"
    assert ref(unesco) == "UNESCO. (2022). Re|penser les politiques culturelles."  # éditeur = auteur : pas répété
    anonyme = Source(type="page_web", annee="2021", titre="Les jardins à Bruxelles",
                     champs={"site": "Visit Brussels", "url": "https://visit.brussels/jardins", "consulte_le": "3 octobre 2026"})
    assert ref(anonyme) == ("Les jardins à Bruxelles. (2021). Visit Brussels. "
                            "Consulté le 3 octobre 2026 de https://visit.brussels/jardins")
    assert apa.citation(anonyme, R).segments[1] == ("Les jardins à Bruxelles", True)


def test_communication_personnelle_hors_bibliographie():
    s = Source(type="communication_personnelle", auteurs=[p("Van Damme", "Eric")], annee="2026",
               champs={"date_precise": "13 mars"})
    assert apa.reference(s, R) is None
    assert apa.citation(s, R).texte == "(E. Van Damme, communication personnelle, 13 mars 2026)"
    assert apa.citation(s, R, narrative=True).texte == "E. Van Damme (communication personnelle, 13 mars 2026)"


def test_bibliographie_en_trois_parties_triee():
    sources = [s for s, _ in BIBLIO_PARTIE_1] + [
        Source(type="communication_personnelle", auteurs=[p("Van Damme", "E.")], annee="2026")]
    parties = apa.bibliographie(sources, R, decoupage="trois_parties")
    assert [titre for titre, _ in parties] == ["Références bibliographiques", "Sources non scientifiques", "Sitographie"]
    # Par défaut, la liste unique de l'APA, sans les communications personnelles.
    [(titre, liste)] = apa.bibliographie(sources, R)
    assert titre == "Références" and len(liste) == 20
    scientifiques = [m.texte.split(" (")[0] for _, m in parties[0][1]]
    assert scientifiques[:3] == ["Arrieta, X.", "Barrault, F.", "Harper, Ch."]
    assert scientifiques[-2:] == ["Wisniewski, L., Pichon, L. et Soler, J.-P.", "Zanetti, M."]
    assert len(parties[0][1]) == 17 and len(parties[1][1]) == 2 and len(parties[2][1]) == 1
    assert [m.texte[:6] for _, m in parties[1][1]] == ["Consei", "Région"]
    # Accents ignorés dans le tri, parties vides omises.
    e = Source(type="livre", auteurs=[p("Élie", "A.")], annee="2000", titre="T", champs={"editeur": "E"})
    f = Source(type="livre", auteurs=[p("Dupont", "A.")], annee="2000", titre="T", champs={"editeur": "E"})
    g = Source(type="livre", auteurs=[p("Fabre", "A.")], annee="2000", titre="T", champs={"editeur": "E"})
    assert [m.texte[:5] for _, ms in apa.bibliographie([g, e, f], R) for _, m in ms] == ["Dupon", "Élie,", "Fabre"]


def test_bibliographie_garde_les_lettres_du_texte():
    # Deux Martin 2020 dans les sources, un seul cité : il garde la lettre de ses citations.
    alpha = Source(type="livre", auteurs=[p("Martin", "A.")], annee="2020", titre="Alpha", champs={"editeur": "E"})
    beta = Source(type="livre", auteurs=[p("Martin", "A.")], annee="2020", titre="Bêta", champs={"editeur": "E"})
    lettres = apa.suffixes([alpha, beta])
    [(_, [(source, mise)])] = apa.bibliographie([beta], R, lettres)
    assert source is beta and mise.texte.startswith("Martin, A. (2020b).")


def test_petits_formats():
    assert apa.initiales("Cara Gendel") == "C. G."
    assert apa.initiales("Jean-Pierre") == "J.-P."
    assert apa.initiales("M.-P.") == "M.-P."
    assert apa.initiales("Ch.") == "Ch."
    for ecrit in ("10.9999/esp.171.0073", "DOI : 10.9999/esp.171.0073", "doi:10.9999/esp.171.0073",
                  "https://dx.doi.org/10.9999/esp.171.0073"):
        assert apa.doi_en_url(ecrit) == "https://doi.org/10.9999/esp.171.0073", ecrit


def test_chaque_type_a_ses_champs_et_sa_partie():
    from memoire.modele import TYPES_SOURCE
    assert set(apa.CHAMPS) == set(TYPES_SOURCE)
    assert set(apa.SECTION_DU_TYPE) == set(TYPES_SOURCE) - {"communication_personnelle"}
    for type_ in TYPES_SOURCE:  # aucun type ne plante, même presque vide
        s = Source(type=type_, auteurs=[p("Martin", "A.")], annee="2020", titre="Titre")
        apa.citation(s, R)
        apa.reference(s, R)


def test_homonymes_distingues_par_leurs_initiales():
    """APA 7 § 8.20 et 9.46 : J. Martin et P. Martin sont deux personnes. Pas de lettres a/b,
    mais les initiales dans la citation, et J. avant P. dans la bibliographie."""
    livre = lambda id_, prenom, annee, titre: Source(type="livre", id=id_, auteurs=[{"nom": "Martin", "prenom": prenom}],
                                                      annee=annee, titre=titre, champs={"editeur": "PUF"})
    jean, pierre = livre("j", "Jean", "2020", "Zoé"), livre("p", "Pierre", "2010", "Alice")
    jean_bis = livre("j2", "J.", "2020", "Autre livre")  # même personne, prénom abrégé
    sources = [jean, pierre, jean_bis]
    assert apa.suffixes(sources) == {"j2": "a", "j": "b"}  # a/b seulement entre les livres de J. Martin
    assert apa.homonymes(sources) == {"j", "p", "j2"}
    assert apa.citation(jean, R, suffixe="b", avec_initiales=True, page_debut="3").texte == "(J. Martin, 2020b, p. 3)"
    assert apa.etiquette(pierre, R, avec_initiales=True) == "P. Martin (2010)"
    ordre = [s.id for _, membres in apa.bibliographie(sources, R) for s, _ in membres]
    assert ordre == ["j2", "j", "p"]  # J. (2020a, 2020b) avant P. (2010)
    # Un prénom manquant ne fait pas un homonyme ; une organisation non plus.
    sans_prenom = Source(type="livre", id="x", auteurs=[{"nom": "Martin"}], annee="2021", titre="T", champs={"editeur": "E"})
    assert apa.homonymes([jean, sans_prenom]) == set()


if __name__ == "__main__":
    lancer(globals())
