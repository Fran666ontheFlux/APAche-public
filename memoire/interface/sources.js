"use strict";

// Écrans Sources : la liste, puis la fiche d'une source et ses extraits.
// Chargé avant app.js, dont il utilise les outils (h, api, essayer, toast,
// etat, rendre…) : ils ne sont appelés qu'après le chargement des deux fichiers.

// Le texte de travail collé dans une fiche n'est pas enregistré dans le
// mémoire (il pèserait lourd sur Drive) : il reste le temps de la session.
const textesDeTravail = new Map();
let minuterieApercu = null;

const typeDe = (cle) => etat.schema.types.find((t) => t.cle === cle);
const copie = (x) => JSON.parse(JSON.stringify(x));

// --- Adresses : #/extraits, #/sources, #/sources/<id>, #/projet ------------------

function lireAdresse() {
  const m = location.hash.match(/^#\/(extraits|plan|projet|sources|bibliographie)(?:\/(\w+))?$/);
  // La bibliothèque de sources s'ouvre d'abord : l'outil sert aussi sans mémoire en cours.
  return m ? { vue: m[1], source: m[1] === "sources" ? m[2] || null : null } : { vue: "sources", source: null };
}

function allerA(adresse) {
  if (location.hash === adresse) chargerVue();
  else location.hash = adresse;  // hashchange → chargerVue
}

async function chargerVue() {
  if (!etat.statut?.ouvert || etat.ferme) return;
  const { vue, source } = lireAdresse();
  etat.vue = vue;
  etat.editeur = null;
  const nouvelle = etat.ouvrirReference;
  etat.ouvrirReference = false;
  await essayer(async () => {
    if (vue === "sources" && source) {
      const fiche = await api("GET", `/api/sources/${source}`);
      // Formulaire de référence ouvert d'office pour une nouvelle source ou s'il
      // manque quelque chose. Décidé à l'ouverture seulement : il ne doit pas se
      // refermer sous les doigts quand le dernier champ manquant est rempli.
      etat.referenceOuverte = nouvelle || fiche.a_completer.length > 0;
      ouvrirFiche(fiche);
      if (!etat.donnees) etat.donnees = await api("GET", "/api/projet");
      etat.plan = await api("GET", "/api/plan");  // pour « Partie du plan » dans l'éditeur d'extrait
    } else if (vue === "plan") {
      etat.fiche = null;
      if (!etat.donnees) etat.donnees = await api("GET", "/api/projet");
      await chargerPlan();
    } else if (vue === "sources") {
      etat.fiche = null;
      etat.listeSources = (await api("GET", "/api/sources")).sources;
    } else if (vue === "bibliographie") {
      etat.fiche = null;
      await chargerBibliographie();
    } else if (vue === "extraits") {
      etat.fiche = null;
      if (!etat.donnees) etat.donnees = await api("GET", "/api/projet");
      await chargerGrille();
    } else {
      etat.fiche = null;
      etat.donnees = await api("GET", "/api/projet");  // les comptes d'extraits ont pu changer
    }
    rendre();
    window.scrollTo(0, 0);
    // Venu de la grille par « Modifier » : aller à l'extrait et l'ouvrir.
    const vise = etat.extraitVise && etat.fiche?.extraits.find((e) => e.id === etat.extraitVise);
    etat.extraitVise = null;
    if (vise) {
      modifierExtrait(vise);
      document.querySelector(".editeur-extrait")?.scrollIntoView({ block: "center" });
    }
  });
}
window.addEventListener("hashchange", chargerVue);

function ouvrirFiche(vue) {
  etat.fiche = vue;
  etat.brouillon = copie(vue.source);
}

// --- Copie vers Google Docs -----------------------------------------

// `mise.html` vient du serveur, déjà échappé (apa.py) : seul l'italique y est du balisage.
async function copier(mise, message) {
  try {
    await navigator.clipboard.write([new ClipboardItem({
      // Une citation se colle dans une phrase (<span>) ; la bibliographie arrive en paragraphes (<p>).
      "text/html": new Blob([mise.html.startsWith("<p>") ? mise.html : `<span>${mise.html}</span>`], { type: "text/html" }),
      "text/plain": new Blob([mise.texte], { type: "text/plain" }),
    })]);
  } catch (e) {
    // Secours (navigateur ancien, permission refusée) : copier une sélection garde l'italique.
    const zone = h("div", { contentEditable: "true", style: { position: "fixed", left: "-9999px", top: "0" } });
    zone.innerHTML = mise.html;
    document.body.append(zone);
    const plage = document.createRange();
    plage.selectNodeContents(zone);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(plage);
    const reussi = document.execCommand("copy");
    selection.removeAllRanges();
    zone.remove();
    if (!reussi) { toast("Le navigateur a refusé la copie. Sélectionne le texte et fais Ctrl+C.", true); return; }
  }
  toast(message);
}

function htmlServeur(balise, attributs, mise) {
  const el = h(balise, attributs);
  el.innerHTML = mise.html;  // voir copier() : déjà échappé côté serveur
  return el;
}

// --- Liste des sources ------------------------------------------------------------

function vueSources() {
  return etat.fiche ? vueFiche() : vueListe();
}

function vueListe() {
  const toutes = etat.listeSources || [];
  const f = sansAccents(etat.rechercheSources || "");
  const filtre = etat.filtreSources || "toutes";
  const liste = toutes.filter((s) => (!f || sansAccents(`${s.etiquette} ${s.titre}`).includes(f))
    && (filtre !== "a_completer" || s.a_completer.length)
    && (filtre !== "partie1" || s.citee_partie1));
  const aCompleter = toutes.filter((s) => s.a_completer.length).length;

  const recherche = h("label", { className: "recherche", icone: "loupe" },
    h("input", { placeholder: "Auteur, titre…", value: etat.rechercheSources || "", "data-cle": "filtre-sources",
      "aria-label": "Chercher une source",
      oninput: (e) => { etat.rechercheSources = e.target.value; rendre(); },
      onkeydown: (e) => { if (e.key === "Escape") { etat.rechercheSources = ""; e.target.blur(); rendre(); } } }),
    h("kbd", {}, "/"));
  const segment = (cle, libelle) => h("button", { className: filtre === cle ? "actif" : "",
    onclick: () => { etat.filtreSources = cle; rendre(); } }, libelle);

  let corps;
  if (!toutes.length) {
    corps = h("div", { className: "vide" },
      h("h3", {}, "Aucune source pour l'instant"),
      h("p", {}, "Ajoute ce que tu lis (un article, un livre, une page web…) et garde-en les passages utiles : "
        + "ils seront là, avec leur page et leur référence APA, le jour où un travail en aura besoin."),
      h("div", { className: "rangee" },
        h("button", { className: "bouton principal", icone: "plus", onclick: nouvelleSource }, "Nouvelle source"),
        h("button", { className: "bouton", onclick: () => allerA("#/projet") }, "Importer des notes existantes")));
  } else {
    corps = h("div", { className: "liste-sources" },
      liste.map(ligneSource),
      !liste.length && h("p", { className: "aide" }, "Aucune source ne correspond."));
  }
  return h("div", {},
    h("div", { className: "section-tete tete-page" },
      h("h1", {}, "Sources"),
      h("span", { className: "compte-page" }, pluriel(toutes.length, "source")),
      h("div", { className: "actions" }, toutes.length ? recherche : null,
        toutes.length ? h("button", { className: "bouton principal", icone: "plus", onclick: nouvelleSource }, "Nouvelle source") : null)),
    toutes.some((s) => s.a_fichier) ? rechercheDansFichiers() : null,
    rechTexte.resultats ? resultatsDansFichiers() : [
      toutes.length ? h("div", { className: "segments filtres-sources" },
        segment("toutes", "Toutes"),
        segment("a_completer", `À compléter (${aCompleter})`),
        segment("partie1", "Déjà citées")) : null,
      corps]);
}

// --- Recherche dans le texte des fichiers joints ------------------------------------

// Propre à ce fichier : `etat` (app.js) n'existe pas encore quand sources.js se charge.
const rechTexte = { q: "", resultats: null, enCours: false, progression: null };

async function lancerRechercheFichiers() {
  const r = rechTexte;
  if (!r.q.trim()) { r.resultats = null; rendre(); return; }
  r.enCours = true;
  r.progression = null;
  rendre();
  // Les fichiers pas encore lus le sont par tranches de quelques secondes, pour montrer où on en est.
  for (;;) {
    const p = await essayer(() => api("POST", "/api/recherche/indexer"));
    if (!p) { r.enCours = false; rendre(); return; }
    if (!p.restants) break;
    r.progression = p;
    rendre();
  }
  const resultats = await essayer(() => api("GET", `/api/recherche?q=${encodeURIComponent(r.q)}`));
  r.enCours = false;
  r.progression = null;
  r.resultats = resultats;
  rendre();
}

function rechercheDansFichiers() {
  const r = rechTexte;
  return h("div", { className: "recherche-fichiers" },
    h("label", { className: "recherche", icone: "loupe" },
      h("input", { placeholder: "Chercher dans le texte des fichiers joints (PDF, Word)…", value: r.q, "data-cle": "recherche-fichiers",
        "aria-label": "Chercher dans le texte des fichiers joints",
        oninput: (e) => { r.q = e.target.value; if (!r.q) { r.resultats = null; rendre(); } },
        onkeydown: (e) => {
          if (e.key === "Enter") lancerRechercheFichiers();
          if (e.key === "Escape") { r.q = ""; r.resultats = null; e.target.blur(); rendre(); }
        } })),
    r.enCours ? h("span", { className: "indice" }, r.progression
      ? `Lecture des fichiers : ${r.progression.total - r.progression.restants} sur ${r.progression.total}…`
      : "Recherche…") : h("span", { className: "indice" }, h("kbd", {}, "Entrée"), " pour chercher"));
}

function resultatsDansFichiers() {
  const { resultats, non_lus: nonLus, trop } = rechTexte.resultats;
  const groupes = new Map();
  for (const x of resultats) {
    if (!groupes.has(x.source_id)) groupes.set(x.source_id, { etiquette: x.etiquette, pages: [] });
    groupes.get(x.source_id).pages.push(x);
  }
  const passage = (x) => {
    const morceaux = [];
    let position = 0;
    for (const [debut, fin] of x.surlignes) {
      if (debut < position) continue;
      morceaux.push(x.passage.slice(position, debut), h("mark", {}, x.passage.slice(debut, fin)));
      position = fin;
    }
    morceaux.push(x.passage.slice(position));
    return [x.coupe_debut ? "…" : "", ...morceaux, x.coupe_fin ? "…" : ""];
  };
  return h("div", { className: "resultats-fichiers" },
    h("div", { className: "tete-resultats" },
      h("strong", {}, resultats.length ? `${resultats.length} page${resultats.length > 1 ? "s" : ""} dans ${pluriel(groupes.size, "source")}`
        : "Rien trouvé dans les fichiers joints."),
      trop ? h("span", { className: "indice" }, " · les 200 premières : précise ta recherche") : null,
      nonLus ? h("span", { className: "indice" }, ` · ${pluriel(nonLus, "fichier")} pas encore lu`) : null,
      h("button", { className: "bouton discret petit", onclick: () => { rechTexte.resultats = null; rechTexte.q = ""; rendre(); } },
        "Revenir à la liste")),
    [...groupes].map(([id, g]) => h("section", { className: "groupe-resultats" },
      h("a", { className: "etiquette-source", href: `#/sources/${id}` }, g.etiquette),
      g.pages.map((x) => h("button", { className: "resultat-page", onclick: () => { etat.pageVisee = x.page; allerA(`#/sources/${id}`); } },
        h("span", { className: "puce" }, x.page ? `p. ${x.page}` : "texte"),
        h("span", { className: "passage" }, passage(x)))))));
}

function ligneSource(s) {
  const ouvrir = () => allerA(`#/sources/${s.id}`);
  return h("div", { className: "ligne-source", role: "link", tabIndex: 0, onclick: ouvrir,
    onkeydown: (e) => { if (e.key === "Enter") ouvrir(); } },
    h("div", { className: "qui" },
      h("span", { className: "etiquette-source" }, s.etiquette),
      // Sans auteur, l'étiquette est déjà le titre : ne pas le répéter.
      s.titre && !s.etiquette.startsWith(s.titre) && h("span", { className: "titre-source" }, s.titre)),
    h("div", { className: "marques" },
      s.a_completer.length ? h("span", { className: "puce alerte", title: "À compléter : " + s.a_completer.join(", ") }, "à compléter") : null,
      s.citee_partie1 ? h("span", { className: "puce", title: "Déjà citée : dans la bibliographie même sans extrait intégré" },
        "déjà citée") : null,
      s.a_fichier ? h("span", { className: "puce discrete", title: "Un PDF ou un Word est joint" }, "fichier") : null,
      h("span", { className: "puce discrete" }, s.libelle_type),
      h("span", { className: "compte" }, s.nb_extraits ? `${pluriel(s.nb_extraits, "extrait")}${s.nb_integres ? ` · ${s.nb_integres} intégré${s.nb_integres > 1 ? "s" : ""}` : ""}` : "aucun extrait")));
}

async function nouvelleSource() {
  const vue = await essayer(() => api("POST", "/api/sources", { type: "article_revue" }));
  if (!vue) return;
  etat.ouvrirReference = true;
  etat.focusApres = "source-type";
  allerA(`#/sources/${vue.cree}`);
}

// --- Fiche d'une source -------------------------------------------------------------

function vueFiche() {
  const f = etat.fiche;
  const s = f.source;
  const statuts = h("div", { className: "segments", role: "radiogroup", "aria-label": "Où en es-tu ?" },
    etat.schema.statuts.map((st) => h("button", { className: s.statut === st.cle ? "actif" : "",
      onclick: () => enregistrerSource({ statut: st.cle }) }, st.libelle)));

  return h("div", { className: "fiche" },
    h("button", { className: "bouton discret petit retour", onclick: () => allerA("#/sources") }, "← Sources"),
    h("h1", { className: "titre-fiche" }, f.etiquette),
    h("div", { className: "sous-fiche" },
      statuts,
      h("label", { className: "case", title: "Citée ailleurs dans ton travail (une première partie, un travail préparatoire…) : "
        + "elle entre dans la bibliographie même sans extrait intégré." },
        h("input", { type: "checkbox", checked: s.citee_partie1, onchange: (e) => enregistrerSource({ citee_partie1: e.target.checked }) }),
        "Déjà citée")),
    carteReference(),
    sectionTexteDeTravail(),
    sectionExtraits(),
    h("div", { className: "pied-fiche" },
      h("button", { className: "bouton danger petit", onclick: supprimerSource }, "Supprimer cette source")));
}

function carteReference() {
  const f = etat.fiche;
  const ouverte = etat.referenceOuverte;
  return h("section", { className: "carte-reference" },
    h("div", { className: "reference-apercu" },
      f.reference ? htmlServeur("p", { className: "notice", id: "apercu-reference" }, f.reference)
        : h("p", { className: "aide", id: "apercu-reference" }, "Un entretien ou un échange personnel se cite dans le texte seulement, jamais dans la bibliographie."),
      h("div", { className: "actions-reference" },
        f.reference && h("button", { className: "bouton petit", onclick: () => copier(etat.fiche.reference, "Référence copiée") }, "Copier la référence"),
        h("button", { className: "bouton discret petit", icone: "crayon", "aria-expanded": String(ouverte),
          onclick: () => { etat.referenceOuverte = !ouverte; rendre(); } }, ouverte ? "Fermer" : "Modifier"))),
    h("div", { id: "manques-reference" }, manques(f.a_completer)),
    ouverte ? formulaireSource() : null);
}

function manques(liste) {
  return liste.length ? h("p", { className: "manques" }, "À compléter : " + liste.join(" · ")) : null;
}

function formulaireSource() {
  const b = etat.brouillon;
  const type = typeDe(b.type);
  const champTexte = (cle, libelle, valeur, surSaisie, surChangement, { long = false } = {}) =>
    h("div", { className: "champ" + (long ? " large" : "") },
      h("label", { htmlFor: `source-${cle}` }, libelle),
      h(long ? "textarea" : "input", { id: `source-${cle}`, className: "entree", value: valeur || "", "data-cle": `source-${cle}`,
        rows: long ? 2 : undefined,
        oninput: (e) => { surSaisie(e.target.value); apercuDiffere(); },
        onchange: surChangement }));

  const champType = (c) => {
    const valeur = b.champs[c.cle];
    if (c.genre === "case") {
      return h("label", { className: "case large" },
        h("input", { type: "checkbox", checked: Boolean(valeur),
          onchange: (e) => { if (e.target.checked) b.champs[c.cle] = true; else delete b.champs[c.cle]; enregistrerChamps(); } }),
        c.libelle);
    }
    if (c.genre === "personnes") {
      if (!Array.isArray(b.champs[c.cle])) b.champs[c.cle] = [];
      return h("div", { className: "champ large" }, h("label", {}, c.libelle),
        editeurPersonnes(b.champs[c.cle], enregistrerChamps, { cle: `source-${c.cle}`, ajout: "Ajouter un directeur" }));
    }
    return champTexte(c.cle, c.libelle, valeur, (v) => { b.champs[c.cle] = v; }, enregistrerChamps,
      { long: c.cle === "titre_ouvrage" });
  };
  const obligatoires = type.champs.filter((c) => c.obligatoire);
  const facultatifs = type.champs.filter((c) => !c.obligatoire);
  const replie = document.querySelector("details.facultatifs")?.open;

  return h("div", { className: "formulaire-source" },
    barreEnLigne(b),
    h("div", { className: "champ large" },
      h("label", { htmlFor: "source-type" }, "Quel type de source ?"),
      h("select", { id: "source-type", className: "entree", "data-cle": "source-type",
        onchange: (e) => { b.type = e.target.value; enregistrerSource({ type: b.type }); } },
        etat.schema.types.map((t) => h("option", { value: t.cle, selected: t.cle === b.type }, t.libelle)))),
    h("div", { className: "champ large" }, h("label", {}, b.type === "communication_personnelle" ? "Avec qui ?" : "Auteurs"),
      editeurPersonnes(b.auteurs, () => enregistrerSource({ auteurs: personnesPleines(b.auteurs) }), { cle: "source-auteurs" })),
    champTexte("annee", "Année", b.annee, (v) => { b.annee = v; }, () => enregistrerSource({ annee: b.annee.trim() })),
    b.type !== "communication_personnelle"
      ? champTexte("titre", "Titre", b.titre, (v) => { b.titre = v; }, () => enregistrerSource({ titre: b.titre.trim() }), { long: true })
      : null,
    obligatoires.map(champType),
    facultatifs.length ? h("details", { className: "facultatifs large", open: replie ?? facultatifs.some((c) => b.champs[c.cle]) },
      h("summary", {}, `Autres détails (facultatif) : ${facultatifs.map((c) => c.libelle.split(" (")[0].toLowerCase()).join(", ")}`),
      h("div", { className: "grille-champs" }, facultatifs.map(champType))) : null);
}

// --- Compléter depuis un DOI ou un ISBN ------------------------------------
// Le seul geste de l'outil qui sort sur internet : désactivé par défaut, autorisé une
// fois en connaissance de cause, puis déclenché clic par clic. Seul l'identifiant part.

const serviceDe = (identifiant) => (/10\./.test(identifiant) ? "CrossRef (crossref.org)"
  : "Open Library (openlibrary.org) et au catalogue de la BnF (catalogue.bnf.fr)");

async function chercherEnLigne() {
  const b = etat.brouillon;
  const identifiant = (etat.identifiantEnLigne ?? (b.champs.doi || b.champs.isbn || "")).trim();
  if (!identifiant) { toast("Indique un DOI (10.…) ou un ISBN.", true); return; }
  if (!etat.donnees?.projet.recherche_en_ligne) {
    const accord = await demander(`Chercher en ligne envoie cet identifiant, et seulement lui, à ${serviceDe(identifiant)} : `
      + `« ${identifiant} ». Aucun nom, aucun extrait, aucune note ne quitte ton PC, mais ce service saura quel ouvrage `
      + "tu as cherché. Activer la recherche en ligne ? Tu pourras la désactiver dans l'écran Projet.",
      { oui: "Activer et chercher" });
    if (!accord) return;
    const projet = await essayer(() => api("PATCH", "/api/projet", { recherche_en_ligne: true }));
    if (!projet) return;
    etat.donnees = projet;
  }
  etat.rechercheEnCours = true;
  rendre();
  const reponse = await essayer(() => api("POST", "/api/en-ligne", { identifiant }));
  etat.rechercheEnCours = false;
  etat.propositionEnLigne = reponse;
  rendre();
}

async function appliquerEnLigne(mode) {
  const p = etat.propositionEnLigne.proposition;
  const s = etat.fiche.source;
  let changements;
  if (mode === "remplacer") {
    changements = { type: p.type, auteurs: p.auteurs, annee: p.annee, titre: p.titre, champs: { ...s.champs, ...p.champs } };
  } else {
    // Compléter : ne touche à rien de ce que l'utilisateur a déjà rempli.
    changements = { champs: { ...p.champs, ...Object.fromEntries(Object.entries(s.champs).filter(([, v]) => v !== "" && v !== null)) } };
    if (!personnesPleines(s.auteurs).length && p.auteurs.length) changements.auteurs = p.auteurs;
    if (!s.annee.trim() && p.annee) changements.annee = p.annee;
    if (!s.titre.trim() && p.titre) changements.titre = p.titre;
  }
  await enregistrerSource(changements);
  etat.brouillon = copie(etat.fiche.source);
  etat.propositionEnLigne = null;
  etat.identifiantEnLigne = null;
  toast(mode === "remplacer" ? "Référence remplacée" : "Champs vides complétés");
  rendre();
}

function barreEnLigne(b) {
  const valeur = etat.identifiantEnLigne ?? (b.champs.doi || b.champs.isbn || "");
  const r = etat.propositionEnLigne;
  const personnes = (liste) => liste.map((a) => a.organisation || [a.nom, a.prenom].filter(Boolean).join(", ")).join(" · ");
  return h("div", { className: "en-ligne large" },
    h("div", { className: "rangee" },
      h("input", { className: "entree", value: valeur, "data-cle": "source-identifiant", "aria-label": "DOI ou ISBN",
        placeholder: "DOI ou ISBN (ex. 10.1177/… ou 978-2-…)",
        oninput: (e) => { etat.identifiantEnLigne = e.target.value; },
        onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); chercherEnLigne(); } } }),
      h("button", { className: "bouton", disabled: etat.rechercheEnCours, onclick: chercherEnLigne },
        etat.rechercheEnCours ? "Recherche…" : "Compléter en ligne")),
    h("span", { className: "detail" }, etat.donnees?.projet.recherche_en_ligne
      ? `Envoie seulement l'identifiant à ${serviceDe(valeur || "10.")}.`
      : "Désactivé : rien ne sort de ton PC tant que tu ne l'autorises pas."),
    r ? h("div", { className: "proposition-en-ligne" },
      h("div", { className: "etiquette-termes" }, `Trouvé par ${r.proposition.service}`),
      r.reference ? htmlServeur("p", { className: "notice" }, r.reference) : null,
      h("dl", { className: "champs-proposes" },
        [["Auteurs", personnes(r.proposition.auteurs)], ["Année", r.proposition.annee], ["Titre", r.proposition.titre]]
          .filter(([, v]) => v).flatMap(([cle, v]) => [h("dt", {}, cle), h("dd", {}, v)])),
      h("div", { className: "rangee" },
        h("button", { className: "bouton principal", onclick: () => appliquerEnLigne("remplacer") }, "Remplacer par ces informations"),
        h("button", { className: "bouton", onclick: () => appliquerEnLigne("completer") }, "Compléter les champs vides"),
        h("button", { className: "bouton discret", onclick: () => { etat.propositionEnLigne = null; rendre(); } }, "Fermer"))) : null);
}

const personnesPleines = (liste) => liste
  .map((p) => (p.organisation !== undefined ? { organisation: p.organisation.trim() } : { nom: (p.nom || "").trim(), prenom: (p.prenom || "").trim() }))
  .filter((p) => p.organisation || p.nom);

// Personnes ou organisations : une ligne chacune. Les lignes vides restent
// dans le brouillon (on est en train de les remplir) mais ne sont pas enregistrées.
function editeurPersonnes(liste, enregistrer, { cle, ajout = "Ajouter un auteur" }) {
  if (!liste.length) liste.push({ nom: "", prenom: "" });
  return h("div", { className: "personnes" },
    liste.map((p, i) => {
      const estOrganisation = p.organisation !== undefined;
      const entree = (champ, placeholder, classe) => h("input", { className: "entree " + (classe || ""), value: p[champ] || "",
        placeholder, "aria-label": placeholder, "data-cle": `${cle}-${i}-${champ}`,
        oninput: (e) => { p[champ] = e.target.value; apercuDiffere(); }, onchange: enregistrer });
      return h("div", { className: "personne" },
        estOrganisation ? entree("organisation", "Organisation (ex. UNESCO)", "organisation")
          : [entree("nom", "Nom", "nom"), entree("prenom", "Prénom ou initiales", "prenom")],
        h("button", { className: "bouton discret petit", title: estOrganisation ? "C'est une personne" : "C'est une organisation (UNESCO, un collectif…)",
          onclick: () => {
            liste[i] = estOrganisation ? { nom: p.organisation || "", prenom: "" } : { organisation: [p.prenom, p.nom].filter(Boolean).join(" ") };
            enregistrer(); rendre();
          } }, estOrganisation ? "Personne" : "Organisation"),
        h("button", { className: "icone", icone: "croix", title: "Retirer", "aria-label": "Retirer",
          onclick: () => { liste.splice(i, 1); enregistrer(); rendre(); } }));
    }),
    h("button", { className: "bouton discret petit", icone: "plus",
      onclick: () => { liste.push({ nom: "", prenom: "" }); etat.focusApres = `${cle}-${liste.length - 1}-nom`; rendre(); } }, ajout));
}

function enregistrerChamps() {
  const propres = {};
  for (const [cle, valeur] of Object.entries(etat.brouillon.champs)) {
    if (Array.isArray(valeur)) { if (personnesPleines(valeur).length) propres[cle] = personnesPleines(valeur); }
    else if (typeof valeur === "string") { if (valeur.trim()) propres[cle] = valeur.trim(); }
    else if (valeur) propres[cle] = valeur;
  }
  return enregistrerSource({ champs: propres });
}

// Le brouillon garde ce qui est en cours de saisie ; seule la fiche (référence,
// étiquette) est remplacée par la réponse, pour ne pas écraser une frappe en cours.
async function enregistrerSource(changements) {
  const id = etat.fiche.source.id;
  try {
    const vue = await api("PATCH", `/api/sources/${id}`, changements);
    etat.fiche = vue;
    if ("type" in changements || "statut" in changements || "citee_partie1" in changements) etat.brouillon = copie(vue.source);
  } catch (e) {
    toast(e.message, true);
    etat.brouillon = copie(etat.fiche.source);
  }
  rendre();
}

function apercuDiffere() {
  clearTimeout(minuterieApercu);
  minuterieApercu = setTimeout(async () => {
    if (!etat.fiche) return;
    const b = etat.brouillon;
    try {
      const r = await api("POST", "/api/sources/apercu", { id: b.id, type: b.type, auteurs: personnesPleines(b.auteurs),
        annee: b.annee, titre: b.titre, champs: b.champs });
      const cible = document.getElementById("apercu-reference");
      if (cible && r.reference) cible.innerHTML = r.reference.html;  // échappé côté serveur
      document.getElementById("manques-reference")?.replaceChildren(manques(r.a_completer) || "");
    } catch (e) { /* aperçu seulement : l'erreur éventuelle s'affichera à l'enregistrement */ }
  }, 250);
}

async function supprimerSource() {
  const { source, etiquette, extraits } = etat.fiche;
  const message = extraits.length
    ? `« ${etiquette} » a ${pluriel(extraits.length, "extrait")}, qui seront supprimés avec elle. Supprimer quand même ?`
    : `Supprimer « ${etiquette} » ?`;
  if (!(await demander(message, { oui: "Supprimer", danger: true }))) return;
  if (!(await essayer(() => api("DELETE", `/api/sources/${source.id}?confirme=1`)))) return;
  toast("Source supprimée");
  allerA("#/sources");
}

// --- Texte de travail -----------------------------------------------------------------

function sectionTexteDeTravail() {
  if (etat.fiche.fichier) return sectionFichier();
  const id = etat.fiche.source.id;
  // Ouvert d'office : c'est là qu'on glisse le PDF, il doit se voir.
  const ouvert = document.querySelector("details.texte-travail")?.open ?? true;
  const zone = h("textarea", { className: "entree zone-travail", "data-cle": "texte-travail", rows: 7,
    placeholder: "Colle ici le texte que tu lis (depuis un PDF, une page web…), puis sélectionne un passage et crée un extrait.",
    value: textesDeTravail.get(id) || "", oninput: (e) => textesDeTravail.set(id, e.target.value) });
  return h("details", { className: "repli texte-travail", open: ouvert },
    h("summary", {}, h("span", { className: "chevron", icone: "chevron" }), "Texte de travail",
      h("span", { className: "resume" }, "glisser un PDF, ou coller du texte")),
    h("div", { className: "corps-travail" },
      h("div", { className: "zone-depot" },
        h("p", {}, h("strong", {}, "Glisse ici le PDF ou le Word de ce texte"),
          " : il est copié dans ton dossier de données, et son texte s'affiche page par page."),
        boutonChoisirFichier("Choisir un fichier")),
      h("p", { className: "aide petite" }, "Ou colle le texte ci-dessous (il n'est gardé que jusqu'à la fermeture de l'outil) :"),
      zone,
      h("div", { className: "rangee" },
        h("button", { className: "bouton principal", icone: "plus", onclick: () => nouvelExtrait("exige") }, "Extrait depuis la sélection"),
        h("span", { className: "indice" }, h("kbd", {}, "N")))));
}

// --- Fichier joint (étape 7) -------------------------------------------------------------

// Texte lu dans le fichier joint, par source : la lecture d'un gros PDF prend du temps.
const lectures = new Map();

function boutonChoisirFichier(libelle, classe = "bouton") {
  const entree = h("input", { type: "file", accept: ".pdf,.docx", hidden: true,
    onchange: (e) => { if (e.target.files[0]) deposerFichier(e.target.files[0]); } });
  return h("span", {}, entree, h("button", { className: classe, onclick: () => entree.click() }, libelle));
}

async function deposerFichier(fichier) {
  const f = etat.fiche;
  if (f.fichier && !(await demander(`Remplacer « ${f.fichier.nom} » par « ${fichier.name} » ? Ton fichier d'origine n'est pas touché.`,
    { oui: "Remplacer" }))) return;
  toast(`Copie de « ${fichier.name} »…`);
  let reponse, donnees = {};
  try {
    reponse = await fetch(`/api/sources/${f.source.id}/fichier`, { method: "POST", body: fichier,
      headers: { "Content-Type": "application/octet-stream", "X-Nom-Fichier": encodeURIComponent(fichier.name) } });
    donnees = await reponse.json();
  } catch (e) {
    toast("L'outil ne répond plus. Relance APAche, puis recharge cette page.", true);
    return;
  }
  if (!reponse.ok) { toast(donnees.erreur || "Erreur inattendue.", true); return; }
  lectures.delete(f.source.id);
  if (etat.fiche?.source.id === f.source.id) etat.fiche = donnees;
  toast("Fichier joint");
  rendre();
}

async function chargerTexte(id) {
  lectures.set(id, { chargement: true });
  let lecture;
  try { lecture = { donnees: await api("GET", `/api/sources/${id}/texte`) }; }
  catch (e) { lecture = { erreur: e.message }; }
  lectures.set(id, lecture);
  if (etat.fiche?.source.id === id) rendre();
}

// `ou` : quelle page du PDF porte ce numéro (les pages d'avant, couverture ou sommaire, n'en ont pas).
const debutNumeros = (p, ou) => (ou > 1 ? `la page ${ou} du PDF porte le numéro ${p} ; les pages d'avant ne sont pas numérotées.`
  : `la 1re page est la page ${p}.`);
const NUMEROTATIONS = {
  entetes: (p, ou) => `Pages numérotées d'après les numéros imprimés dans le PDF : ${debutNumeros(p, ou)}`,
  pdf: (p, ou) => `Numérotation inscrite dans le PDF : ${debutNumeros(p, ou)}`,
  manuelle: (p) => `Tu as indiqué que la 1re page du PDF est la page ${p}.`,
  a_verifier: () => "Aucun numéro de page imprimé trouvé : l'outil compte les pages du PDF (1, 2, 3…). "
    + "Si le texte commence par exemple page 953 de la revue, indique-le :",
};

function sectionFichier() {
  const f = etat.fiche;
  const id = f.source.id;
  const lecture = lectures.get(id);
  if (!lecture && f.fichier.present) chargerTexte(id);
  const d = lecture?.donnees;

  let corps;
  if (!f.fichier.present) {
    corps = h("div", { className: "bandeau erreur", icone: "alerte" }, h("div", { className: "texte" },
      "Le fichier est introuvable dans le dossier de données. Si tu l'as ajouté sur un autre PC, attends la fin de "
      + "la synchronisation, puis recharge la page."));
  } else if (!lecture || lecture.chargement) {
    corps = h("p", { className: "aide" }, "Lecture du fichier…");
  } else if (lecture.erreur) {
    corps = h("div", { className: "bandeau erreur", icone: "alerte" }, h("div", { className: "texte" }, lecture.erreur));
  } else if (d.scanne) {
    corps = h("div", { className: "bandeau", icone: "alerte" }, h("div", { className: "texte" },
      h("strong", {}, "Ce PDF est une image scannée"), "\n",
      "Son texte n'est pas lisible tel quel. Il reste joint à la source (« Ouvrir »). ",
      blocOcr(id, d)));
  } else {
    const numerotation = d.type === "pdf" ? h("div", { className: "numerotation" + (d.numerotation === "a_verifier" ? " a-verifier" : "") },
      h("span", {}, NUMEROTATIONS[d.numerotation](d.premiere, d.premiere_pdf)),
      h("label", { className: "premiere-page" }, "1re page du PDF = page ",
        h("input", { className: "entree", value: f.source.premiere_page || "", placeholder: d.premiere_pdf > 1 ? "" : d.premiere, inputMode: "numeric",
          "data-cle": "premiere-page", "aria-label": "Numéro imprimé de la première page du PDF",
          onchange: async (e) => {
            const valeur = e.target.value.trim();
            if (valeur && !/^\d+$/.test(valeur)) { toast("Indique un numéro de page (ex. 953).", true); return; }
            await enregistrerSource({ premiere_page: valeur });
            lectures.delete(id);
            rendre();
          } }))) : null;
    // Venu d'une recherche dans les fichiers : amener la page trouvée sous les yeux.
    if (etat.pageVisee !== undefined && etat.pageVisee !== null) {
      const page = etat.pageVisee;
      etat.pageVisee = null;
      setTimeout(() => {
        const cible = [...document.querySelectorAll(".page-fichier")].find((el) => el.dataset.page === page);
        if (cible) {
          cible.scrollIntoView({ block: "start" });
          cible.classList.add("eclat-page");
        }
      });
    }
    corps = [
      numerotation,
      h("div", { className: "pages-fichier", "data-defilement": `fichier-${id}` },
        d.pages.map((p) => h("section", { className: "page-fichier" + (p.ocr ? " ocr" : ""), "data-page": p.etiquette },
          h("p", {}, p.texte)))),
      d.pages_ocr ? h("p", { className: "aide petite" }, `${pluriel(d.pages_ocr, "page")} lue${d.pages_ocr > 1 ? "s" : ""} par OCR : `
        + "des lettres peuvent être mal reconnues. Vérifie une citation sur le PDF (« Ouvrir ») avant de la reprendre.") : null,
      d.pages_vides ? h("div", { className: "numerotation a-verifier" },
        `${pluriel(d.pages_vides, "page")} sans texte lisible (des images). `, blocOcr(id, d)) : null,
      h("div", { className: "rangee" },
        h("button", { className: "bouton principal", icone: "plus", onclick: () => nouvelExtrait("exige") }, "Extrait depuis la sélection"),
        h("span", { className: "indice" }, "sélectionne un passage, puis ", h("kbd", {}, "N"), " : la page est remplie toute seule")),
    ];
  }
  return h("details", { className: "repli texte-travail", open: document.querySelector("details.texte-travail")?.open ?? true },
    h("summary", {}, h("span", { className: "chevron", icone: "chevron" }), f.fichier.nom,
      h("span", { className: "resume" }, d ? (d.type === "pdf" ? pluriel(d.pages.length, "page") : "Word") : "")),
    h("div", { className: "corps-travail" },
      h("div", { className: "rangee" },
        h("a", { className: "bouton petit", href: `/api/sources/${id}/fichier`, target: "_blank", rel: "noopener" }, "Ouvrir"),
        boutonChoisirFichier("Remplacer", "bouton discret petit")),
      corps));
}

// --- OCR des pages scannées ------------------------------------------------------------

let ocrDisponible = null;  // réponse de /api/ocr, demandée une fois : Tesseract est là ou pas
const ocrEnCours = new Map();  // source → progression

async function lancerOcr(id) {
  ocrEnCours.set(id, { faites: 0, total: null });
  rendre();
  for (;;) {
    let p;
    try { p = await api("POST", `/api/sources/${id}/ocr`); }
    catch (e) { toast(e.message, true); break; }
    ocrEnCours.set(id, p);
    rendre();
    if (!p.restantes) { toast("Texte lu par OCR"); break; }
  }
  ocrEnCours.delete(id);
  lectures.delete(id);  // relire le texte, désormais complété
  rendre();
}

function blocOcr(id, d) {
  if (ocrDisponible === null) {
    ocrDisponible = { chargement: true };
    api("GET", "/api/ocr").then((r) => { ocrDisponible = r; rendre(); }).catch(() => { ocrDisponible = { disponible: false, message: "" }; });
  }
  const enCours = ocrEnCours.get(id);
  if (enCours) {
    return h("span", { className: "progression-ocr" },
      enCours.total ? `Lecture par OCR : page ${enCours.faites} sur ${enCours.total}…` : "Lecture par OCR…");
  }
  if (!ocrDisponible || ocrDisponible.chargement) return null;
  if (!ocrDisponible.disponible) {
    return h("span", {}, "Crée tes extraits à la main avec « Nouvel extrait ». ",
      ocrDisponible.message ? h("span", { className: "indice" }, ocrDisponible.message) : null);
  }
  const pages = d.pages_vides || d.pages.length;
  return h("span", {},
    h("button", { className: "bouton petit", onclick: () => lancerOcr(id) },
      `Lire le texte par OCR (${pluriel(pages, "page")}, quelques secondes chacune)`),
    ocrDisponible.message ? h("span", { className: "indice" }, " ", ocrDisponible.message) : null);
}

// Passage sélectionné dans le texte du fichier, avec ses pages de début et de fin.
function selectionDansFichier() {
  const selection = getSelection();
  const panneau = document.querySelector(".pages-fichier");
  if (!selection || selection.isCollapsed || !panneau || !panneau.contains(selection.anchorNode)) return null;
  const pageDe = (noeud) => (noeud.nodeType === 1 ? noeud : noeud.parentElement)?.closest("[data-page]")?.dataset.page || "";
  let debut = pageDe(selection.anchorNode), fin = pageDe(selection.focusNode);
  if (selection.anchorNode.compareDocumentPosition(selection.focusNode) & Node.DOCUMENT_POSITION_PRECEDING) [debut, fin] = [fin, debut];
  const texte = selection.toString()
    .replace(/(\p{L})-\s*\n\s*(\p{Ll})/gu, "$1$2")  // mot coupé en fin de ligne
    .replace(/\s*\n\s*/g, " ").replace(/\s{2,}/g, " ").trim();
  return texte ? { texte, page_debut: debut, page_fin: fin !== debut ? fin : "" } : null;
}

// --- Extraits -----------------------------------------------------------------------

function sectionExtraits() {
  const extraits = etat.fiche.extraits;
  const nouveau = etat.editeur && !etat.editeur.id;
  return h("section", { className: "section section-extraits" },
    h("div", { className: "section-tete" },
      h("h2", {}, "Extraits"), h("span", { className: "compte-page" }, extraits.length ? String(extraits.length) : ""),
      h("div", { className: "actions" },
        h("button", { className: "bouton", icone: "plus", onclick: () => nouvelExtrait(false) }, "Nouvel extrait"))),
    nouveau ? editeurExtrait() : null,
    !extraits.length && !nouveau
      ? h("p", { className: "aide" }, "Aucun extrait. Colle le texte dans « Texte de travail » et sélectionne un passage, ou crée un extrait à la main.")
      : null,
    h("div", { className: "liste-extraits" },
      extraits.map((e) => (etat.editeur?.id === e.id ? editeurExtrait() : carteExtrait(e)))));
}

// depuisSelection : "exige" (bouton : il faut une sélection), "si_possible"
// (touche N : la sélection s'il y en a une, sinon un extrait vide), ou rien.
function nouvelExtrait(depuisSelection) {
  let pris = { texte: "", page_debut: "", page_fin: "" };
  if (depuisSelection) {
    const zone = document.querySelector('[data-cle="texte-travail"]');
    const dansZone = zone ? zone.value.slice(zone.selectionStart, zone.selectionEnd).trim() : "";
    pris = selectionDansFichier() || (dansZone ? { ...pris, texte: dansZone } : pris);
  }
  if (depuisSelection === "exige" && !pris.texte) {
    toast("Sélectionne d'abord un passage dans le texte.", true);
    return;
  }
  const texte = pris.texte;
  etat.editeur = { id: null, suggestions: [], touches: new Set(), auto: new Set(),
    brouillon: { texte, page_debut: pris.page_debut, page_fin: pris.page_fin,
      nature: texte ? "citation" : "paraphrase", mots_cles: [], note: "", integre: false, auteur_origine: null,
      section_plan: null } };
  if (texte) suggererMots();
  etat.focusApres = !texte ? "extrait-texte" : pris.page_debut ? "extrait-note" : "extrait-page_debut";
  rendre();
  document.querySelector(".editeur-extrait")?.scrollIntoView({ block: "center" });
}

function modifierExtrait(e) {
  etat.editeur = { id: e.id, suggestions: [], touches: new Set(), auto: new Set(), brouillon: { texte: e.texte, page_debut: e.page_debut, page_fin: e.page_fin, nature: e.nature,
    mots_cles: [...e.mots_cles], note: e.note, integre: e.integre, auteur_origine: e.auteur_origine ? copie(e.auteur_origine) : null,
    section_plan: e.section_plan || null } };
  etat.focusApres = "extrait-texte";
  rendre();
  suggererMots();
}

let minuterieSuggestions = null;

function suggererMotsDiffere() {
  clearTimeout(minuterieSuggestions);
  minuterieSuggestions = setTimeout(suggererMots, 350);
}

// Mots-clés reconnus dans le passage. Pour un nouvel extrait, ils sont
// pré-cochés ; l'utilisateur garde la main : un mot-clé qu'il a touché n'est plus
// jamais coché ou décoché à sa place. Pour un extrait existant, simple proposition.
async function suggererMots() {
  const ed = etat.editeur;
  if (!ed) return;
  let reponse;
  try { reponse = await api("POST", "/api/suggestions", { texte: brut(ed.brouillon.texte) }); }
  catch (e) { return; }  // une suggestion en moins n'empêche pas de travailler
  if (etat.editeur !== ed) return;
  ed.suggestions = reponse.suggestions;
  if (!ed.id) {
    const suggeres = new Set(ed.suggestions.map((s) => s.id));
    const choisis = ed.brouillon.mots_cles;
    for (const id of [...ed.auto]) {
      if (!suggeres.has(id) && !ed.touches.has(id)) { choisis.splice(choisis.indexOf(id), 1); ed.auto.delete(id); }
    }
    for (const id of suggeres) {
      if (!ed.touches.has(id) && !choisis.includes(id)) { choisis.push(id); ed.auto.add(id); }
    }
  }
  rendre();
}

// Le passage avec ses termes reconnus surlignés.
function termesReconnus(ed) {
  const texte = brut(ed.brouillon.texte);
  const plages = ed.suggestions.flatMap((s) => s.passages.map(([debut, fin]) => [debut, fin, s.libelle]))
    .sort((a, b) => a[0] - b[0]);
  if (!plages.length) return null;
  const morceaux = [];
  let position = 0;
  for (const [debut, fin, libelle] of plages) {
    if (debut < position) continue;
    morceaux.push(texte.slice(position, debut), h("mark", { title: `→ ${libelle}` }, texte.slice(debut, fin)));
    position = fin;
  }
  morceaux.push(texte.slice(position));
  return h("div", { className: "termes-reconnus" },
    h("span", { className: "etiquette-termes" }, "Termes reconnus"),
    h("p", {}, morceaux));
}

function editeurExtrait() {
  const b = etat.editeur.brouillon;
  const fermer = () => { etat.editeur = null; rendre(); };
  const texte = (cle, props) => h(props.rows ? "textarea" : "input", { id: `extrait-${cle}`, className: "entree", value: b[cle] || "",
    "data-cle": `extrait-${cle}`, oninput: (e) => { b[cle] = e.target.value; if (cle === "texte") suggererMotsDiffere(); }, ...props });
  const origine = b.auteur_origine;
  return h("div", { className: "editeur-extrait", "data-id": etat.editeur.id || "nouveau" },
    h("div", { className: "champ" }, h("label", { htmlFor: "extrait-texte" }, "Passage"),
      champEnrichi({ cle: "extrait-texte", id: "extrait-texte", valeur: b.texte, placeholder: "Le texte de l'extrait, ou ton idée",
        surSaisie: (valeur) => { b.texte = valeur; suggererMotsDiffere(); } }),
      termesReconnus(etat.editeur)),
    h("div", { className: "rangee-champs" },
      h("div", { className: "champ" }, h("label", {}, "Nature"),
        h("div", { className: "segments" }, etat.schema.natures.map((n) => h("button", { className: b.nature === n.cle ? "actif" : "",
          onclick: () => { b.nature = n.cle; rendre(); } }, n.libelle)))),
      h("div", { className: "champ petit" }, h("label", { htmlFor: "extrait-page_debut" }, b.nature === "citation" ? "Page (obligatoire)" : "Page"),
        texte("page_debut", { placeholder: "45" })),
      h("div", { className: "champ petit" }, h("label", { htmlFor: "extrait-page_fin" }, "à la page"),
        texte("page_fin", { placeholder: "facultatif" }))),
    h("div", { className: "champ" }, h("label", {}, "Mots-clés"), choixMotsCles(b.mots_cles, etat.editeur)),
    etat.plan?.sections.length ? h("div", { className: "champ" },
      h("label", { htmlFor: "extrait-section" }, "Partie du plan"),
      h("select", { id: "extrait-section", className: "entree choix", "data-cle": "extrait-section",
        onchange: (e) => { b.section_plan = e.target.value || null; } },
        h("option", { value: "", selected: !b.section_plan }, "Selon ses mots-clés seulement"),
        etat.plan.sections.map((s) => h("option", { value: s.id, selected: b.section_plan === s.id },
          `${s.niveau === 2 ? "   " : ""}${s.numero}  ${s.titre}`))),
      h("span", { className: "detail" }, "Pour ranger ce passage dans une partie, même si ses mots-clés ne l'y mènent pas.")) : null,
    h("div", { className: "champ" }, h("label", { htmlFor: "extrait-note" }, "Note"),
      texte("note", { rows: 2, placeholder: "Pourquoi ce passage t'intéresse, où il pourrait servir…" })),
    // Ouvert s'il y a vraiment un auteur d'origine ; sinon l'état choisi par l'utilisateur est gardé.
    h("details", { className: "origine", open: document.querySelector(".editeur-extrait details.origine")?.open
      ?? Boolean(origine?.auteurs?.some((a) => a.nom || a.organisation)) },
      h("summary", {}, "L'auteur cite quelqu'un d'autre ? (source secondaire)"),
      h("p", { className: "aide" }, "Ex. Martin cite Piaget : l'outil écrira (Piaget, 1952, cité dans Martin, 2020). Seul Martin ira dans la bibliographie."),
      (() => {
        const o = b.auteur_origine || { auteurs: [], annee: "" };
        b.auteur_origine = o;
        return h("div", { className: "rangee-champs" },
          h("div", { className: "champ large" }, editeurPersonnes(o.auteurs, () => {}, { cle: "extrait-origine", ajout: "Ajouter un auteur cité" })),
          h("div", { className: "champ petit" }, h("label", { htmlFor: "extrait-origine-annee" }, "Année"),
            h("input", { id: "extrait-origine-annee", className: "entree", value: o.annee || "", "data-cle": "extrait-origine-annee",
              oninput: (e) => { o.annee = e.target.value; } })));
      })()),
    h("div", { className: "pied-editeur" },
      h("label", { className: "case" }, h("input", { type: "checkbox", checked: b.integre, onchange: (e) => { b.integre = e.target.checked; } }),
        "Déjà intégré au mémoire"),
      h("span", { className: "indice" }, h("kbd", {}, "Ctrl"), "+", h("kbd", {}, "Entrée")),
      h("button", { className: "bouton discret", onclick: fermer }, "Annuler"),
      h("button", { className: "bouton principal", onclick: enregistrerExtrait }, etat.editeur.id ? "Enregistrer" : "Créer l'extrait")));
}

function choixMotsCles(choisis, ed) {
  const suggestions = new Map((ed?.suggestions || []).map((s) => [s.id, s]));
  const tous = [];
  for (const t of themes().sort((a, b) => a.libelle.localeCompare(b.libelle, "fr"))) {
    tous.push(t, ...enfantsDe(t.id).sort((a, b) => a.libelle.localeCompare(b.libelle, "fr")));
  }
  const ajout = ajoutMotCle("editeur", (id) => {
    if (!choisis.includes(id)) choisis.push(id);
    ed?.touches.add(id);
    ed?.auto.delete(id);
  }, "nouveau mot-clé");
  if (!tous.length) return h("div", { className: "choix-mots" }, ajout);
  const f = sansAccents(etat.filtreMots || "");
  const visibles = tous.filter((m) => choisis.includes(m.id) || !f || [m.libelle, ...m.synonymes].some((x) => sansAccents(x).includes(f)));
  return h("div", { className: "choix-mots" },
    tous.length > 12 && h("input", { className: "entree filtre-mots", placeholder: "Filtrer les mots-clés", value: etat.filtreMots || "",
      "data-cle": "extrait-filtre-mots", oninput: (e) => { etat.filtreMots = e.target.value; rendre(); } }),
    visibles.map((m) => {
      const actif = choisis.includes(m.id);
      const suggestion = suggestions.get(m.id);
      return h("button", { className: "pastille" + (actif ? " selectionne choisi" : "") + (suggestion ? " suggere" : ""),
        style: { "--c": couleurDe(m) }, "aria-pressed": String(actif), "data-cle": `mot-${m.id}`,
        title: suggestion ? `Suggéré d'après « ${suggestion.termes.join(" », « ")} »` : null,
        onclick: () => {
          if (actif) choisis.splice(choisis.indexOf(m.id), 1); else choisis.push(m.id);
          ed?.touches.add(m.id);
          ed?.auto.delete(m.id);
          rendre();
        } }, m.parent_id ? m.libelle : h("strong", {}, m.libelle), suggestion ? h("span", { className: "marque-suggestion", "aria-label": "suggéré" }, "✦") : null);
    }),
    ajout);
}

async function enregistrerExtrait() {
  const ed = etat.editeur;
  const b = { ...ed.brouillon, texte: ed.brouillon.texte.trim(), page_debut: ed.brouillon.page_debut.trim(),
    page_fin: ed.brouillon.page_fin.trim(), note: ed.brouillon.note.trim() };
  const auteurs = personnesPleines(b.auteur_origine?.auteurs || []);
  b.auteur_origine = auteurs.length ? { auteurs, annee: (b.auteur_origine.annee || "").trim() } : null;
  if (!brut(b.texte).trim()) { toast("L'extrait est vide : colle ou écris le passage.", true); return; }
  const source = etat.fiche.source.id;
  const vue = await essayer(() => (ed.id ? api("PATCH", `/api/extraits/${ed.id}`, b) : api("POST", `/api/sources/${source}/extraits`, b)));
  if (!vue) return;
  const id = ed.id || vue.cree;
  etat.fiche = vue;
  etat.editeur = null;
  etat.filtreMots = "";
  toast(ed.id ? "Extrait enregistré" : "Extrait créé");
  rendre();
  const carte = document.querySelector(`.extrait[data-id="${id}"]`);
  if (carte) { carte.scrollIntoView({ block: "center" }); carte.classList.add("eclat"); }
}

async function basculerIntegre(e) {
  const vue = await essayer(() => api("PATCH", `/api/extraits/${e.id}`, { integre: !e.integre }));
  if (vue) { etat.fiche = vue; rendre(); }
}

async function supprimerExtrait(e) {
  if (!(await demander("Supprimer cet extrait ?", { oui: "Supprimer", danger: true }))) return;
  const vue = await essayer(() => api("DELETE", `/api/extraits/${e.id}`));
  if (vue) { etat.fiche = vue; toast("Extrait supprimé"); rendre(); }
}

function carteExtrait(e) {
  const deplie = etat.deplies?.has(e.id);
  const long = brut(e.texte).length > 600;
  const pages = e.page_debut ? `p. ${e.page_debut}${e.page_fin ? "-" + e.page_fin : ""}` : "sans page";
  const nature = etat.schema.natures.find((n) => n.cle === e.nature).libelle;
  return h("article", { className: "extrait" + (e.integre ? " integre" : ""), "data-id": e.id },
    h("div", { className: "tete-extrait" },
      h("span", { className: "puce" + (e.page_debut ? "" : " discrete") }, pages),
      h("span", { className: "puce discrete" }, nature),
      e.mots_cles.map((id) => motParId(id)).filter(Boolean).map((m) => h("span", { className: "pastille", style: { "--c": couleurDe(m), cursor: "default" } }, m.libelle)),
      h("label", { className: "case integre-case", title: "Coché : le passage est déjà dans le mémoire. Il apparaît barré." },
        h("input", { type: "checkbox", checked: e.integre, onchange: () => basculerIntegre(e) }), "Intégré")),
    h("p", { className: "texte-extrait" + (long && !deplie ? " replie" : "") }, misEnForme(e.texte)),
    long ? h("button", { className: "bouton discret petit", onclick: () => {
      etat.deplies = etat.deplies || new Set();
      if (deplie) etat.deplies.delete(e.id); else etat.deplies.add(e.id);
      rendre();
    } }, deplie ? "Réduire" : "Tout afficher") : null,
    e.note ? h("p", { className: "note-extrait" }, e.note) : null,
    h("div", { className: "actions-extrait" },
      e.citation ? h("button", { className: "bouton copie", title: "Copier la citation entre parenthèses",
        onclick: () => copier(e.citation, "Citation copiée") }, e.citation.texte) : null,
      e.narrative ? h("button", { className: "bouton discret petit", title: e.narrative.texte,
        onclick: () => copier(e.narrative, "Forme narrative copiée") }, "Narrative") : null,
      e.avec_texte ? h("button", { className: "bouton discret petit", title: "« passage » (Auteur, année, p.)",
        onclick: () => copier(e.avec_texte, "Citation et passage copiés") }, "Avec le passage") : null,
      h("span", { className: "espace" }),
      h("button", { className: "bouton discret petit", icone: "crayon", onclick: () => modifierExtrait(e) }, "Modifier"),
      h("button", { className: "bouton discret petit danger", onclick: () => supprimerExtrait(e) }, "Supprimer")));
}

// --- Raccourcis propres aux écrans Sources ------------------------------------------------

// Renvoie true si la touche a été traitée.
function raccourciSources(e) {
  if (etat.vue !== "sources") return false;
  // Éditeur d'extrait ouvert : où que soit le focus (un clic sur un mot-clé redessine l'écran).
  if (etat.editeur && !document.querySelector(".modale-fond")) {
    if (e.key === "Escape") { etat.editeur = null; rendre(); return true; }
    if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); enregistrerExtrait(); return true; }
  }
  const zoneTravail = e.target.matches?.('[data-cle="texte-travail"]');
  const enSaisie = e.target.matches?.("input, textarea, select, [contenteditable]") && !zoneTravail;
  if (enSaisie || e.altKey || e.metaKey || e.ctrlKey || document.querySelector(".modale-fond")) return false;
  if (e.key === "/" && !etat.fiche && !zoneTravail) {
    e.preventDefault();
    document.querySelector('[data-cle="filtre-sources"]')?.focus();
    return true;
  }
  if (e.key.toLowerCase() === "n" && (!zoneTravail || e.target.selectionStart !== e.target.selectionEnd)) {
    // Dans la zone de travail, N ne crée un extrait que si un passage est sélectionné (sinon on tape un « n »).
    e.preventDefault();
    if (etat.fiche) nouvelExtrait("si_possible"); else nouvelleSource();
    return true;
  }
  return false;
}


// --- Glisser-déposer ---------------------------------------------------------------------

// Un fichier lâché hors de la fiche ne doit pas faire ouvrir le PDF par le
// navigateur (on perdrait l'écran en cours) : on l'intercepte partout.
let profondeurGlisser = 0;
const porteDesFichiers = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
window.addEventListener("dragenter", (e) => {
  if (!porteDesFichiers(e)) return;
  profondeurGlisser += 1;
  document.body.classList.toggle("depot-actif", Boolean(etat.fiche && etat.vue === "sources"));
});
window.addEventListener("dragleave", () => {
  profondeurGlisser = Math.max(0, profondeurGlisser - 1);
  if (!profondeurGlisser) document.body.classList.remove("depot-actif");
});
window.addEventListener("dragover", (e) => { if (porteDesFichiers(e)) e.preventDefault(); });
window.addEventListener("drop", (e) => {
  if (!porteDesFichiers(e)) return;
  e.preventDefault();
  profondeurGlisser = 0;
  document.body.classList.remove("depot-actif");
  const fichier = e.dataTransfer.files[0];
  if (!fichier) return;
  if (etat.fiche && etat.vue === "sources") deposerFichier(fichier);
  else toast("Ouvre d'abord la fiche de la source, puis glisse le fichier dessus.", true);
});
