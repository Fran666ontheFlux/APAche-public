"use strict";

// Grille des extraits, le cœur de l'usage : retrouver les bons
// extraits au moment d'écrire. Tous les extraits arrivent en une fois, citations
// déjà mises en forme ; les filtres s'appliquent dans le navigateur, sans attente.
// Chargé avant app.js, dont il utilise les outils.

const PAR_PAGE = 60;
const grille = {
  donnees: null,        // réponse de /api/extraits
  recherche: "",
  mots: new Set(),      // mots-clés choisis (un thème couvre ses sous-thèmes)
  tousLesMots: false,   // plusieurs mots-clés : au moins un (défaut) ou tous
  sansMot: false,       // « à classer »
  source: "", type: "", annee: "", nature: "",
  integre: "tous",      // tous | non | oui
  partie1: false,
  vue: "extrait",       // extrait | source | couverture
  limite: PAR_PAGE,
  sourcesOuvertes: new Set(),  // vue « par source » : sources dont on a déplié les extraits
  limitesSources: new Map(),   // vue « par source » : cartes montrées par source, si plus que PAR_PAGE
};

// --- Recherche sans accents, avec surlignage -------------------------------------

const VARIANTES = { a: "aàâä", e: "eéèêë", i: "iîï", o: "oôö", u: "uùûü", c: "cç", y: "yÿ" };

function motifRecherche(terme) {
  const mots = sansAccents(terme).split(/\s+/).filter(Boolean);
  if (!mots.length) return null;
  const classe = (ch) => (VARIANTES[ch] ? `[${VARIANTES[ch]}]` : ch.replace(/[.*+?^${}()|[\]\\\/-]/g, "\\$&"));
  return new RegExp(mots.map((m) => [...m].map(classe).join("")).join("|"), "giu");
}

function surligner(texte, motif) {
  if (!motif) return texte;
  const morceaux = [];
  let dernier = 0;
  for (const m of texte.matchAll(motif)) {
    morceaux.push(texte.slice(dernier, m.index), h("mark", {}, m[0]));
    dernier = m.index + m[0].length;
  }
  morceaux.push(texte.slice(dernier));
  return morceaux;
}

// --- Filtres -----------------------------------------------------------------------

function avecSousThemes(id) {
  return new Set([id, ...enfantsDe(id).map((m) => m.id)]);
}

function filtresActifs() {
  const g = grille;
  return Boolean(g.recherche.trim() || g.mots.size || g.sansMot || g.source || g.type || g.annee || g.nature
    || g.integre !== "tous" || g.partie1);
}

function effacerFiltres() {
  Object.assign(grille, { recherche: "", mots: new Set(), tousLesMots: false, sansMot: false, source: "", type: "",
    annee: "", nature: "", integre: "tous", partie1: false, limite: PAR_PAGE, sourcesOuvertes: new Set(),
    limitesSources: new Map() });
  rendre();
}

function extraitsFiltres() {
  const g = grille;
  const { extraits, sources } = g.donnees;
  const mots = sansAccents(g.recherche).split(/\s+/).filter(Boolean);
  const groupes = [...g.mots].map(avecSousThemes);
  return extraits.filter((e) => {
    const s = sources[e.source_id];
    if (mots.length) {
      const dans = sansAccents(`${brut(e.texte)} ${e.note}`);
      if (!mots.every((m) => dans.includes(m))) return false;
    }
    if (g.sansMot && e.mots_cles.length) return false;
    if (groupes.length) {
      const portes = groupes.map((gr) => e.mots_cles.some((m) => gr.has(m)));
      if (g.tousLesMots ? !portes.every(Boolean) : !portes.some(Boolean)) return false;
    }
    if (g.source && e.source_id !== g.source) return false;
    if (g.type && s.type !== g.type) return false;
    if (g.annee && (s.annee || "s. d.") !== g.annee) return false;
    if (g.nature && e.nature !== g.nature) return false;
    if (g.integre === "non" && e.integre) return false;
    if (g.integre === "oui" && !e.integre) return false;
    if (g.partie1 && !s.citee_partie1) return false;
    return true;
  });
}

function changerFiltre(changements) {
  Object.assign(grille, changements, { limite: PAR_PAGE });
  rendre();
}

// --- Chargement --------------------------------------------------------------------

async function chargerGrille() {
  const d = await api("GET", "/api/extraits");
  // Ordre de lecture : par source (comme on y pense), puis dans l'ordre du document.
  const rang = new Map(Object.values(d.sources)
    .sort((a, b) => a.etiquette.localeCompare(b.etiquette, "fr")).map((s, i) => [s.id, i]));
  d.extraits = d.extraits.map((e, i) => ({ e, i }))
    .sort((a, b) => rang.get(a.e.source_id) - rang.get(b.e.source_id) || a.i - b.i).map(({ e }) => e);
  grille.donnees = d;
  if (grille.source && !d.sources[grille.source]) grille.source = "";
  for (const id of grille.sourcesOuvertes) if (!d.sources[id]) grille.sourcesOuvertes.delete(id);
  grille.plan = await api("GET", "/api/plan");  // pour la couverture des parties du plan
}

// --- Couverture des thèmes -------------------------------------------------------
// Où la matière abonde, où elle manque : par thème, combien d'extraits, combien déjà
// intégrés, de combien de sources. Un tableau d'abord (les nombres sont écrits), avec
// une barre pour comparer d'un coup d'œil ; cliquer un thème ouvre ses extraits.

const SEUIL_PEU = 5;  // en dessous : « peu de matière »

function comptesCouverture(extraits, sources) {
  const liste = [...extraits];
  return {
    total: liste.length,
    integres: liste.filter((e) => e.integre).length,
    sources: new Set(liste.map((e) => e.source_id)).size,
    avecPage: liste.filter((e) => e.page_debut).length,
    sourcesNoms: [...new Set(liste.map((e) => sources[e.source_id]?.etiquette).filter(Boolean))],
  };
}

function barreCouverture(c, maximum, titre) {
  const largeur = (n) => `${maximum ? (100 * n) / maximum : 0}%`;
  const reste = c.total - c.integres;
  return h("div", { className: "barre-couverture", title: `${titre} : ${c.integres} intégrés, ${reste} à intégrer` },
    c.integres ? h("span", { className: "segment integres", style: { width: largeur(c.integres) } }) : null,
    reste ? h("span", { className: "segment a-integrer", style: { width: largeur(reste) } }) : null);
}

function vueCouverture() {
  const { extraits, sources } = grille.donnees;
  const lignes = [];
  for (const t of themes()) {
    const ids = avecSousThemes(t.id);
    lignes.push({ mot: t, c: comptesCouverture(extraits.filter((e) => e.mots_cles.some((m) => ids.has(m))), sources),
      enfants: enfantsDe(t.id).map((m) => ({ mot: m, c: comptesCouverture(extraits.filter((e) => e.mots_cles.includes(m.id)), sources) })) });
  }
  lignes.sort((a, b) => b.c.total - a.c.total || a.mot.libelle.localeCompare(b.mot.libelle, "fr"));
  const sansMot = extraits.filter((e) => !e.mots_cles.length);
  const maximum = Math.max(1, ...lignes.map((l) => l.c.total));
  const ouvrir = (id) => { changerFiltre({ vue: "extrait", mots: new Set([id]), sansMot: false }); window.scrollTo(0, 0); };

  const ligne = (mot, c, sous) => h("tr", { className: sous ? "sous" : "", tabIndex: 0, role: "link",
    onclick: () => ouvrir(mot.id), onkeydown: (e) => { if (e.key === "Enter") ouvrir(mot.id); } },
    h("th", { scope: "row" }, h("span", { className: "pastille-point", style: { "--c": couleurDe(mot) } }), mot.libelle,
      c.total < SEUIL_PEU || (c.total && c.sources < 2)
        ? h("span", { className: "puce alerte peu", title: c.sources < 2 && c.total ? "Tous ses extraits viennent d'une seule source." : "" },
          "⚠ ", c.total < SEUIL_PEU ? "peu de matière" : "une seule source") : null),
    h("td", { className: "nombre" }, c.total),
    h("td", { className: "cellule-barre" }, barreCouverture(c, maximum, mot.libelle)),
    h("td", { className: "nombre" }, c.total - c.integres),
    h("td", { className: "nombre", title: c.sourcesNoms.join(" · ") }, c.sources),
    h("td", { className: "nombre" }, c.avecPage));

  const plan = grille.plan?.sections || [];
  return h("div", { className: "couverture" },
    h("p", { className: "aide" }, "Tes thèmes, du plus nourri au moins nourri. Clique sur un thème pour voir ses extraits. "
      + "Un extrait qui porte plusieurs thèmes compte pour chacun."),
    h("div", { className: "legende-couverture", "aria-hidden": "true" },
      h("span", {}, h("span", { className: "echantillon integres" }), "Intégrés"),
      h("span", {}, h("span", { className: "echantillon a-integrer" }), "À intégrer")),
    h("div", { className: "tableau-defilant" }, h("table", { className: "table-couverture" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Thème"), h("th", { scope: "col", className: "nombre" }, "Extraits"),
        h("th", { scope: "col" }, h("span", { className: "invisible" }, "Répartition")),
        h("th", { scope: "col", className: "nombre" }, "À intégrer"), h("th", { scope: "col", className: "nombre" }, "Sources"),
        h("th", { scope: "col", className: "nombre" }, "Avec page"))),
      h("tbody", {}, lignes.flatMap((l) => [ligne(l.mot, l.c, false), ...l.enfants.map((x) => ligne(x.mot, x.c, true))]),
        sansMot.length ? h("tr", { className: "a-classer", tabIndex: 0, role: "link",
          onclick: () => { changerFiltre({ vue: "extrait", sansMot: true, mots: new Set() }); window.scrollTo(0, 0); } },
          h("th", { scope: "row" }, "Sans mot-clé (à classer)"), h("td", { className: "nombre" }, sansMot.length),
          h("td", {}), h("td", { className: "nombre" }, sansMot.filter((e) => !e.integre).length), h("td", {}), h("td", {})) : null))),
    plan.length ? [
      h("h2", { className: "titre-couverture-plan" }, "Parties du plan"),
      h("div", { className: "tableau-defilant" }, h("table", { className: "table-couverture" },
        h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Partie"), h("th", { scope: "col", className: "nombre" }, "Extraits"),
          h("th", { scope: "col" }, h("span", { className: "invisible" }, "Répartition")),
          h("th", { scope: "col", className: "nombre" }, "À intégrer"))),
        h("tbody", {}, plan.map((s, i) => {
          const c = { total: s.nb_extraits, integres: s.nb_extraits - s.nb_a_integrer };
          const maxPlan = Math.max(1, ...plan.map((x) => x.nb_extraits));
          // Un chapitre dont les sections ont de la matière n'est pas vide pour autant.
          const suite = plan.slice(i + 1);
          const fin = suite.findIndex((x) => x.niveau <= s.niveau);
          const vide = !s.nb_extraits && !(fin < 0 ? suite : suite.slice(0, fin)).some((x) => x.nb_extraits);
          return h("tr", { className: s.niveau === 2 ? "sous" : "", tabIndex: 0, role: "link",
            onclick: () => { etat.sectionChoisie = s.id; allerA("#/plan"); } },
            h("th", { scope: "row" }, h("span", { className: "numero" }, s.numero), " ", s.titre,
              vide ? h("span", { className: "puce alerte peu" }, "⚠ vide") : null),
            h("td", { className: "nombre" }, s.nb_extraits),
            h("td", { className: "cellule-barre" }, barreCouverture(c, maxPlan, s.titre)),
            h("td", { className: "nombre" }, s.nb_a_integrer));
        }))))] : null);
}

// --- Rendu -------------------------------------------------------------------------

function vueGrille() {
  const d = grille.donnees;
  if (!d.extraits.length) {
    return h("div", {},
      h("div", { className: "section-tete tete-page" }, h("h1", {}, "Extraits")),
      h("div", { className: "vide" },
        h("h3", {}, "Aucun extrait pour l'instant"),
        h("p", {}, "Un extrait se garde depuis la fiche d'une source : glisses-y le PDF, sélectionne un passage "
          + "et appuie sur N. Il arrive ici avec sa page et sa citation prête à copier."),
        h("div", { className: "rangee" },
          h("button", { className: "bouton principal", onclick: () => allerA("#/sources") }, "Voir les sources"),
          h("button", { className: "bouton", onclick: () => allerA("#/projet") }, "Importer des notes existantes"))));
  }
  const filtres = extraitsFiltres();
  const integres = filtres.filter((e) => e.integre).length;
  const recherche = h("label", { className: "recherche", icone: "loupe" },
    h("input", { placeholder: "Chercher dans les extraits et les notes", value: grille.recherche, "data-cle": "filtre-extraits",
      "aria-label": "Chercher dans les extraits et les notes",
      oninput: (e) => changerFiltre({ recherche: e.target.value }),
      onkeydown: (e) => { if (e.key === "Escape") { e.target.blur(); changerFiltre({ recherche: "" }); } } }),
    h("kbd", {}, "/"));
  const vues = h("div", { className: "segments", role: "radiogroup", "aria-label": "Présentation" },
    [["extrait", "Par extrait"], ["source", "Par source"], ["couverture", "Couverture"]].map(([cle, libelle]) =>
      h("button", { className: grille.vue === cle ? "actif" : "", onclick: () => changerFiltre({ vue: cle }) }, libelle)));

  if (grille.vue === "couverture") {
    return h("div", { className: "grille" },
      h("div", { className: "section-tete tete-page" },
        h("h1", {}, "Extraits"),
        h("span", { className: "compte-page" }, pluriel(d.extraits.length, "extrait")),
        h("div", { className: "actions" }, vues)),
      vueCouverture());
  }

  return h("div", { className: "grille" },
    h("div", { className: "section-tete tete-page" },
      h("h1", {}, "Extraits"),
      h("span", { className: "compte-page" }, filtresActifs()
        ? `${filtres.length} sur ${d.extraits.length}` : pluriel(d.extraits.length, "extrait"),
        integres ? ` · ${integres} intégré${integres > 1 ? "s" : ""}` : ""),
      h("div", { className: "actions" }, recherche, vues)),
    barreFiltres(),
    filtres.length ? (grille.vue === "source" ? resultatsParSource(filtres) : resultatsParExtrait(filtres))
      : h("div", { className: "vide" }, h("h3", {}, "Aucun extrait ne correspond"),
        h("p", {}, "Retire un filtre, ou cherche un autre mot."),
        h("button", { className: "bouton", onclick: effacerFiltres }, "Effacer les filtres")));
}

function barreFiltres() {
  const g = grille;
  const { extraits, sources } = g.donnees;
  const sansMot = extraits.filter((e) => !e.mots_cles.length).length;

  const pastilles = [];
  for (const t of themes().sort((a, b) => a.libelle.localeCompare(b.libelle, "fr"))) {
    pastilles.push(t, ...enfantsDe(t.id).sort((a, b) => a.libelle.localeCompare(b.libelle, "fr")));
  }
  const mots = h("div", { className: "filtre-mots-cles" },
    pastilles.map((m) => {
      const actif = g.mots.has(m.id);
      return h("button", { className: "pastille" + (actif ? " choisi" : "") + (m.parent_id ? " sous" : ""), style: { "--c": couleurDe(m) },
        "aria-pressed": String(actif), "data-cle": `filtre-mot-${m.id}`,
        title: m.parent_id ? null : "Comprend ses sous-thèmes",
        onclick: () => { const s = new Set(g.mots); if (!s.delete(m.id)) s.add(m.id); changerFiltre({ mots: s, sansMot: false }); } },
        m.libelle);
    }),
    sansMot ? h("button", { className: "pastille a-classer" + (g.sansMot ? " choisi" : ""), "aria-pressed": String(g.sansMot),
      style: { "--c": "var(--encre-3)" },
      onclick: () => changerFiltre({ sansMot: !g.sansMot, mots: new Set() }) }, `À classer (${sansMot})`) : null,
    ajoutMotCle("filtres", () => {}, "nouveau mot-clé"),
    g.mots.size > 1 ? h("div", { className: "segments mini" },
      h("button", { className: g.tousLesMots ? "" : "actif", onclick: () => changerFiltre({ tousLesMots: false }) }, "au moins un"),
      h("button", { className: g.tousLesMots ? "actif" : "", onclick: () => changerFiltre({ tousLesMots: true }) }, "tous")) : null);

  const choix = (cle, libelle, options) => h("select", { className: "entree choix" + (g[cle] ? " actif" : ""), "aria-label": libelle,
    "data-cle": `filtre-${cle}`, onchange: (e) => changerFiltre({ [cle]: e.target.value }) },
    h("option", { value: "" }, libelle),
    options.map(([valeur, texte]) => h("option", { value: valeur, selected: g[cle] === valeur }, texte)));

  const listeSources = Object.values(sources).sort((a, b) => a.etiquette.localeCompare(b.etiquette, "fr"));
  const types = [...new Set(listeSources.map((s) => s.type))].map((t) => [t, sources[Object.keys(sources).find((id) => sources[id].type === t)].libelle_type]);
  const annees = [...new Set(listeSources.map((s) => s.annee || "s. d."))].sort().reverse();

  return h("div", { className: "filtres-grille" },
    mots,
    h("div", { className: "rangee-filtres" },
      choix("source", "Toutes les sources", listeSources.map((s) => [s.id, s.etiquette])),
      choix("annee", "Toutes les années", annees.map((a) => [a, a])),
      choix("type", "Tous les types", types.sort((a, b) => a[1].localeCompare(b[1], "fr"))),
      choix("nature", "Citations, paraphrases, idées", etat.schema.natures.map((n) => [n.cle, n.libelle])),
      h("div", { className: "segments" },
        [["tous", "Tous"], ["non", "À intégrer"], ["oui", "Intégrés"]].map(([cle, libelle]) =>
          h("button", { className: g.integre === cle ? "actif" : "", onclick: () => changerFiltre({ integre: cle }) }, libelle))),
      h("label", { className: "case" }, h("input", { type: "checkbox", checked: g.partie1,
        onchange: (e) => changerFiltre({ partie1: e.target.checked }) }), "Sources déjà citées"),
      filtresActifs() ? h("button", { className: "bouton discret petit", icone: "croix", onclick: effacerFiltres }, "Effacer les filtres") : null));
}

function plusDeResultats(total) {
  if (total <= grille.limite) return null;
  return h("button", { className: "bouton plus-resultats", onclick: () => { grille.limite += PAR_PAGE * 2; rendre(); } },
    `Afficher plus (${total - grille.limite} restant${total - grille.limite > 1 ? "s" : ""})`);
}

function resultatsParExtrait(filtres) {
  const motif = motifRecherche(grille.recherche);
  return h("div", { className: "liste-extraits" },
    filtres.slice(0, grille.limite).map((e) => carteGrille(e, true, motif)),
    plusDeResultats(filtres.length));
}

function resultatsParSource(filtres) {
  const motif = motifRecherche(grille.recherche);
  const groupes = new Map();
  for (const e of filtres) {
    if (!groupes.has(e.source_id)) groupes.set(e.source_id, []);
    groupes.get(e.source_id).push(e);
  }
  // Une ligne par source, repliée : un clic montre ses extraits (au plus PAR_PAGE, puis
  // « Afficher les N autres » propre à la source). Pendant une recherche de texte, les
  // premières sources trouvées se déplient d'elles-mêmes, dans la limite de `grille.limite`
  // cartes ; les suivantes restent repliées, un clic les ouvre.
  const ouvertes = grille.sourcesOuvertes;
  const index = new Map(mots().map((m) => [m.id, m]));
  let budget = motif ? grille.limite : 0;
  const blocs = [...groupes].map(([id, extraits]) => {
    const s = grille.donnees.sources[id];
    const auto = !ouvertes.has(id) && budget > 0;  // déplié par la recherche
    const ouvert = auto || ouvertes.has(id);
    const limite = grille.limitesSources.get(id) || PAR_PAGE;
    const montres = ouvert ? extraits.slice(0, limite) : [];
    if (auto) budget -= montres.length;
    const integres = extraits.filter((e) => e.integre).length;
    // Sans auteur, l'étiquette APA est déjà le titre : ne pas le répéter.
    const titre = s.titre && !s.etiquette.startsWith(s.titre) ? s.titre : "";
    const reste = extraits.length - montres.length;
    return h("section", { className: "groupe-source" + (ouvert ? " ouvert" : "") },
      h("div", { className: "tete-groupe" },
        h("button", { className: "bascule-source", "aria-expanded": String(ouvert), "aria-disabled": String(auto),
          title: auto ? "Recherche en cours : les passages trouvés restent dépliés" : ouvert ? "Replier" : "Voir les extraits de cette source",
          onclick: () => { if (auto) return; if (!ouvertes.delete(id)) ouvertes.add(id); rendre(); } },
          h("span", { className: "chevron", icone: "chevron" }),
          h("span", { className: "resume-source" },
            h("span", { className: "etiquette-source" }, s.etiquette),
            titre ? h("span", { className: "titre-source" }, titre) : null,
            h("span", { className: "compte" }, pluriel(extraits.length, "extrait") + (integres ? ` · ${integres} intégré${integres > 1 ? "s" : ""}` : ""))),
          motsDeLaSource(extraits, index)),
        ouvert ? h("div", { className: "actions-groupe" },
          h("span", { className: "puce discrete" }, s.libelle_type),
          s.citee_partie1 ? h("span", { className: "puce" }, "déjà citée") : null,
          h("a", { className: "bouton discret petit", href: `#/sources/${id}` }, "Ouvrir la fiche"),
          s.reference ? h("button", { className: "bouton discret petit", onclick: () => copier(s.reference, "Référence copiée") }, "Copier la référence") : null) : null),
      montres.length ? h("div", { className: "liste-extraits" }, montres.map((e) => carteGrille(e, false, motif)),
        ouvert && reste > 0 ? h("button", { className: "bouton plus-resultats", onclick: () => {
          grille.limitesSources.set(id, limite + PAR_PAGE * 2);
          rendre();
        } }, `Afficher les ${reste} autre${reste > 1 ? "s" : ""}`) : null) : null);
  });
  const visibles = [...groupes.keys()];
  const tousOuverts = visibles.every((id) => ouvertes.has(id));
  return h("div", { className: "groupes par-source" },
    motif ? null : h("div", { className: "rangee" },
      h("span", { className: "indice" }, pluriel(groupes.size, "source")),
      h("button", { className: "bouton discret petit", onclick: () => {
        // Seulement les sources affichées : celles cachées par un filtre gardent leur état.
        visibles.forEach((id) => (tousOuverts ? ouvertes.delete(id) : ouvertes.add(id)));
        rendre();
      } }, tousOuverts ? "Tout replier" : "Tout déplier")),
    blocs);
}

// Les thèmes d'une source d'un coup d'œil : ses mots-clés, du plus fréquent parmi ses
// extraits au moins fréquent (à égalité, par ordre alphabétique), avec leur nombre.
const MOTS_PAR_SOURCE = 8;

function motsDeLaSource(extraits, index) {
  const comptes = new Map();
  for (const e of extraits) for (const id of new Set(e.mots_cles)) comptes.set(id, (comptes.get(id) || 0) + 1);
  const tries = [...comptes].map(([id, n]) => [index.get(id), n]).filter(([m]) => m)
    .sort((a, b) => b[1] - a[1] || a[0].libelle.localeCompare(b[0].libelle, "fr"));
  if (!tries.length) return h("span", { className: "mots-source vide" }, "aucun mot-clé");
  const reste = tries.length - MOTS_PAR_SOURCE;
  return h("span", { className: "mots-source" },
    tries.slice(0, MOTS_PAR_SOURCE).map(([m, n]) => h("span", { className: "pastille statique", style: { "--c": couleurDe(m) },
      title: `${m.libelle} : ${pluriel(n, "extrait")}` }, m.libelle, h("span", { className: "n" }, n))),
    reste > 0 ? h("span", { className: "plus-mots", title: tries.slice(MOTS_PAR_SOURCE).map(([m, n]) => `${m.libelle} (${n})`).join(", ") },
      `+${reste}`) : null);
}

// Aussi utilisée par le plan (plan.js), avec ses propres sources et sa propre case « intégré ».
function carteGrille(e, avecSource, motif, { sources = grille.donnees.sources, surIntegre = basculerIntegreGrille,
  extra = null } = {}) {
  const s = sources[e.source_id];
  const deplie = etat.deplies?.has(e.id) || Boolean(motif);  // une recherche montre le passage en entier
  const long = brut(e.texte).length > 600;
  const pages = e.page_debut ? `p. ${e.page_debut}${e.page_fin ? "-" + e.page_fin : ""}` : "sans page";
  const nature = etat.schema.natures.find((n) => n.cle === e.nature).libelle;
  return h("article", { className: "extrait" + (e.integre ? " integre" : ""), "data-id": e.id },
    h("div", { className: "tete-extrait" },
      avecSource ? h("a", { className: "source-extrait", href: `#/sources/${e.source_id}`,
        onclick: (ev) => { ev.preventDefault(); ouvrirDansFiche(e); } }, s.etiquette) : null,
      h("span", { className: "puce" + (e.page_debut ? "" : " discrete") }, pages),
      h("span", { className: "puce discrete" }, nature),
      e.mots_cles.map(motParId).filter(Boolean).map((m) => h("button", { className: "pastille", style: { "--c": couleurDe(m) },
        title: `Filtrer sur « ${m.libelle} »`,
        onclick: () => {
          changerFiltre({ mots: new Set([m.id]), sansMot: false });
          if (etat.vue !== "extraits") allerA("#/extraits");  // depuis le plan : ouvrir la grille filtrée
        } }, m.libelle)),
      etat.vue === "extraits" ? ajoutMotCle(`carte-${e.id}`, (id) => ajouterMotGrille(e, id), "mot-clé") : null,
      h("label", { className: "case integre-case", title: "Coché : le passage est déjà dans le mémoire. Il apparaît barré." },
        h("input", { type: "checkbox", checked: e.integre, onchange: () => surIntegre(e) }), "Intégré")),
    extra,
    h("p", { className: "texte-extrait" + (long && !deplie ? " replie" : "") }, misEnForme(e.texte, motif)),
    long && !motif ? h("button", { className: "bouton discret petit", onclick: () => {
      etat.deplies = etat.deplies || new Set();
      if (deplie) etat.deplies.delete(e.id); else etat.deplies.add(e.id);
      rendre();
    } }, deplie ? "Réduire" : "Tout afficher") : null,
    e.note ? h("p", { className: "note-extrait" }, surligner(e.note, motif)) : null,
    h("div", { className: "actions-extrait" },
      e.citation ? h("button", { className: "bouton copie", title: "Copier la citation entre parenthèses",
        onclick: () => copier(e.citation, "Citation copiée") }, e.citation.texte) : null,
      e.narrative ? h("button", { className: "bouton discret petit", title: e.narrative.texte,
        onclick: () => copier(e.narrative, "Forme narrative copiée") }, "Narrative") : null,
      e.avec_texte ? h("button", { className: "bouton discret petit", title: "« passage » (Auteur, année, p.)",
        onclick: () => copier(e.avec_texte, "Citation et passage copiés") }, "Avec le passage") : null,
      s.reference ? h("button", { className: "bouton discret petit", title: "Copier la référence complète de la source",
        onclick: () => copier(s.reference, "Référence copiée") }, "Référence") : null,
      h("span", { className: "espace" }),
      h("button", { className: "bouton discret petit", icone: "crayon", onclick: () => ouvrirDansFiche(e) }, "Modifier")));
}

async function basculerIntegreGrille(e) {
  const vue = await essayer(() => api("PATCH", `/api/extraits/${e.id}`, { integre: !e.integre }));
  if (!vue) return;
  const neuf = vue.extraits.find((x) => x.id === e.id);
  const liste = grille.donnees.extraits;
  liste[liste.indexOf(e)] = neuf;
  rendre();
}

async function ajouterMotGrille(e, id) {
  if (e.mots_cles.includes(id)) return;
  const vue = await essayer(() => api("PATCH", `/api/extraits/${e.id}`, { mots_cles: [...e.mots_cles, id] }));
  if (!vue) return;
  const liste = grille.donnees.extraits;
  liste[liste.indexOf(e)] = vue.extraits.find((x) => x.id === e.id);
}

function ouvrirDansFiche(e) {
  etat.extraitVise = e.id;
  allerA(`#/sources/${e.source_id}`);
}

// Renvoie true si la touche a été traitée.
function raccourciGrille(e) {
  if (etat.vue !== "extraits" || !grille.donnees) return false;
  const enSaisie = e.target.matches?.("input, textarea, select, [contenteditable]");
  if (enSaisie || e.altKey || e.metaKey || document.querySelector(".modale-fond")) return false;
  if ((e.key === "/" && !e.ctrlKey) || (e.key === "k" && e.ctrlKey)) {
    e.preventDefault();
    document.querySelector('[data-cle="filtre-extraits"]')?.focus();
    return true;
  }
  return false;
}
