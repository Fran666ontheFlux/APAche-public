"use strict";

// Toute la vérité est côté serveur : chaque action renvoie les données à jour
// et l'écran est redessiné à partir d'elles. Pas de copie locale à synchroniser.
const etat = {
  statut: null,          // réponse de /api/etat
  donnees: null,         // réponse de /api/projet
  ferme: false,
  vue: "sources",
  filtre: "",
  saisie: null,          // { parent: id | null } quand une saisie rapide est ouverte
  panneau: null,         // id du mot-clé en cours d'édition
  conflitsMasques: false,
  // Import du Google Doc : chemin saisi, aperçu à valider, puis compte rendu.
  import: { chemin: "", apercu: null, choix: new Set(), rapport: null, enCours: false },
  // Écrans Sources (sources.js).
  schema: null,          // types de sources et leurs champs, natures, statuts
  listeSources: null,
  fiche: null,           // réponse de /api/sources/<id> quand une fiche est ouverte
  brouillon: null,       // copie de la source en cours de saisie
  editeur: null,         // { id | null, brouillon } quand un extrait est en édition
  rechercheSources: "",
  filtreSources: "toutes",
  focusApres: null,      // data-cle du champ à activer après le prochain rendu
};

// Teintes choisies pour rester lisibles en pastille, en clair comme en sombre.
const PALETTE = [
  "#4f7cac", "#3f9d8f", "#6a9f4b", "#c29a2e", "#d0773c",
  "#c4545a", "#b0588f", "#7d62b5", "#5a6f8f", "#8c7a5b",
];

const ICONES = {
  grille: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h10"/></svg>',
  sources: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M5 4h9a4 4 0 0 1 4 4v12H9a4 4 0 0 1-4-4z"/><path d="M9 9h5M9 13h3"/></svg>',
  projet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M4 7l8-4 8 4-8 4z"/><path d="M4 12l8 4 8-4M4 17l8 4 8-4"/></svg>',
  biblio: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M6 4v16M10 4v16M15 5l4 14"/></svg>',
  plan: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M9 6h11M13 12h7M13 18h7M4 6h1M8 12h1M8 18h1"/></svg>',
  lune: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg>',
  soleil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  quitter: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3M15 16l4-4-4-4M19 12H9"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  loupe: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4-4"/></svg>',
  croix: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  chevron: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>',
  alerte: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3l10 18H2z" stroke-linejoin="round"/><path d="M12 10v5M12 18v.01"/></svg>',
  coche: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>',
  crayon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>',
};

// --- Petits outils ---------------------------------------------------------

// Construit un élément sans jamais passer de texte utilisateur par innerHTML.
function h(balise, attributs, ...enfants) {
  const el = document.createElement(balise);
  for (const [cle, valeur] of Object.entries(attributs || {})) {
    if (valeur === undefined || valeur === null || valeur === false) continue;
    if (cle.startsWith("on")) el.addEventListener(cle.slice(2), valeur);
    else if (cle === "style" && typeof valeur === "object") {
      // Les variables CSS (--c) ne passent que par setProperty.
      for (const [p, v] of Object.entries(valeur)) {
        if (p.startsWith("--")) el.style.setProperty(p, v); else el.style[p] = v;
      }
    }
    else if (cle === "icone") el.insertAdjacentHTML("afterbegin", ICONES[valeur]);
    else if (cle in el && cle !== "list") el[cle] = valeur;
    else el.setAttribute(cle, valeur === true ? "" : valeur);
  }
  for (const enfant of enfants.flat()) {
    if (enfant === null || enfant === undefined || enfant === false) continue;
    el.append(enfant instanceof Node ? enfant : document.createTextNode(String(enfant)));
  }
  return el;
}

// Ce que fait l'outil, en une phrase : l'accueil, le mode d'emploi, la page du projet.
const ACCROCHE = "Tes sources, tes extraits et tes citations APA au même endroit, sur ton PC, sans compte ni abonnement.";

const sansAccents = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

// --- Gras et italique d'un extrait (voir memoire/mise_en_forme.py) ------------------------
// Le texte ne porte que quatre balises : <b> </b> <i> </i> ; tout le reste est du texte.

const BALISE_FORME = /<(\/?)([bi])>/g;
const brut = (texte) => (texte || "").replace(BALISE_FORME, "");

function morceauxForme(texte) {
  const ouverts = { b: 0, i: 0 };
  const morceaux = [];
  let position = 0;
  for (const m of (texte || "").matchAll(BALISE_FORME)) {
    if (m.index > position) morceaux.push({ texte: texte.slice(position, m.index), gras: ouverts.b > 0, italique: ouverts.i > 0 });
    ouverts[m[2]] = Math.max(0, ouverts[m[2]] + (m[1] ? -1 : 1));
    position = m.index + m[0].length;
  }
  if (position < (texte || "").length) morceaux.push({ texte: texte.slice(position), gras: ouverts.b > 0, italique: ouverts.i > 0 });
  return morceaux;
}

// Le texte mis en forme, avec les passages trouv\u00e9s par `motif` (une recherche) surlign\u00e9s.
function misEnForme(texte, motif) {
  return morceauxForme(texte).map(({ texte: t, gras, italique }) => {
    let noeud = motif ? h("span", {}, surligner(t, new RegExp(motif.source, motif.flags))) : t;
    if (italique) noeud = h("i", {}, noeud);
    if (gras) noeud = h("b", {}, noeud);
    return noeud;
  });
}

// Du champ enrichi (contenteditable) au texte \u00e0 quatre balises.
function versBalises(racine) {
  let sortie = "";
  const parcourir = (noeud, gras, italique) => {
    for (const enfant of noeud.childNodes) {
      if (enfant.nodeType === Node.TEXT_NODE) {
        const t = enfant.nodeValue.replace(/\u00a0/g, " ");
        if (t) sortie += (gras ? "<b>" : "") + (italique ? "<i>" : "") + t + (italique ? "</i>" : "") + (gras ? "</b>" : "");
        continue;
      }
      if (enfant.nodeType !== Node.ELEMENT_NODE) continue;
      const balise = enfant.tagName;
      if (balise === "BR") { sortie += "\n"; continue; }
      const style = enfant.style || {};
      const g = gras || balise === "B" || balise === "STRONG" || /bold|[6-9]00/.test(style.fontWeight || "");
      const i = italique || balise === "I" || balise === "EM" || style.fontStyle === "italic";
      if ((balise === "DIV" || balise === "P") && sortie && !sortie.endsWith("\n")) sortie += "\n";
      parcourir(enfant, g, i);
    }
  };
  parcourir(racine, false, false);
  // Morceaux voisins de m\u00eame style r\u00e9unis (le serveur donne la forme d\u00e9finitive).
  return sortie.replace(/<\/([bi])><\1>/g, "").replace(/<\/i><\/b><b><i>/g, "");
}

// Position du curseur en caract\u00e8res dans un champ enrichi, pour la retrouver apr\u00e8s un rendu.
function curseurDans(el) {
  const sel = getSelection();
  if (!sel.rangeCount || !el.contains(sel.anchorNode)) return null;
  const mesure = (noeud, decalage) => {
    const r = document.createRange();
    r.selectNodeContents(el);
    r.setEnd(noeud, decalage);
    return r.toString().length;
  };
  const r = sel.getRangeAt(0);
  return [mesure(r.startContainer, r.startOffset), mesure(r.endContainer, r.endOffset)];
}

function placerCurseur(el, [debut, fin]) {
  const trouver = (cible) => {
    const marcheur = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let reste = cible, dernier = null;
    for (let n = marcheur.nextNode(); n; n = marcheur.nextNode()) {
      if (reste <= n.nodeValue.length) return [n, reste];
      reste -= n.nodeValue.length;
      dernier = n;
    }
    return dernier ? [dernier, dernier.nodeValue.length] : [el, el.childNodes.length];
  };
  const r = document.createRange();
  r.setStart(...trouver(debut));
  r.setEnd(...trouver(fin));
  const sel = getSelection();
  sel.removeAllRanges();
  sel.addRange(r);
}

// Champ de texte avec gras et italique : Ctrl+B ou Ctrl+G (comme Word en fran\u00e7ais), Ctrl+I.
// Un collage arrive en texte simple (pas les polices et couleurs de la page d'origine).
function champEnrichi({ cle, valeur, placeholder, surSaisie, id }) {
  const appliquer = (commande, el) => { document.execCommand(commande); surSaisie(versBalises(el)); };
  const el = h("div", { id, className: "entree champ-enrichi", contentEditable: "true", role: "textbox", "aria-multiline": "true",
    "data-cle": cle, "data-placeholder": placeholder || "", spellcheck: true,
    oninput: (e) => surSaisie(versBalises(e.currentTarget)),
    onkeydown: (e) => {
      const touche = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (touche === "b" || touche === "g" || touche === "i")) {
        e.preventDefault();
        appliquer(touche === "i" ? "italic" : "bold", e.currentTarget);
      } else if ((e.ctrlKey || e.metaKey) && touche === "u") {
        e.preventDefault();  // pas de soulign\u00e9 : il ne serait pas gard\u00e9
      } else if (e.key === "Enter" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        document.execCommand("insertText", false, "\n");
      }
    },
    onpaste: (e) => {
      e.preventDefault();
      document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
    } }, misEnForme(valeur));
  return h("div", { className: "cadre-enrichi" },
    h("div", { className: "outils-forme", role: "toolbar", "aria-label": "Mise en forme" },
      h("button", { type: "button", className: "bouton-forme", title: "Gras (Ctrl+B ou Ctrl+G)",
        onmousedown: (e) => { e.preventDefault(); appliquer("bold", el); } }, h("b", {}, "G")),
      h("button", { type: "button", className: "bouton-forme", title: "Italique (Ctrl+I)",
        onmousedown: (e) => { e.preventDefault(); appliquer("italic", el); } }, h("i", {}, "I"))),
    el);
}
// « aucune source », « aucun extrait » : les seuls mots féminins passés à pluriel().
const FEMININS = new Set(["source", "référence", "page"]);
const pluriel = (n, mot) => (n === 0 ? `aucun${FEMININS.has(mot) ? "e" : ""} ${mot}` : `${n} ${mot}${n > 1 ? "s" : ""}`);

function toast(message, erreur = false) {
  const el = h("div", { className: "toast" + (erreur ? " erreur" : "") }, message);
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), erreur ? 7000 : 1800);
}

async function api(methode, url, corps) {
  let reponse;
  try {
    reponse = await fetch(url, {
      method: methode,
      headers: { "Content-Type": "application/json" },
      body: corps === undefined ? undefined : JSON.stringify(corps),
    });
  } catch (e) {
    throw new Error("L'outil ne répond plus. Relance APAche, puis recharge cette page.");
  }
  let donnees = {};
  try { donnees = await reponse.json(); } catch (e) { /* réponse vide */ }
  if (reponse.status === 409 && donnees.confirmation) return donnees;
  if (!reponse.ok) throw new Error(donnees.erreur || "Erreur inattendue.");
  return donnees;
}

// Exécute une action et affiche l'erreur éventuelle plutôt que d'échouer en silence.
async function essayer(action) {
  try { return await action(); } catch (e) { toast(e.message, true); rendre(); return null; }
}

function demander(message, { oui = "Confirmer", danger = false } = {}) {
  return new Promise((resoudre) => {
    const fermer = (reponse) => { fond.remove(); document.removeEventListener("keydown", clavier, true); resoudre(reponse); };
    const clavier = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); fermer(false); }
    };
    const bouton = h("button", { className: "bouton " + (danger ? "danger" : "principal"), onclick: () => fermer(true) }, oui);
    const fond = h("div", { className: "modale-fond", onclick: (e) => e.target === fond && fermer(false) },
      h("div", { className: "modale", role: "dialog", "aria-modal": "true" },
        h("p", {}, message),
        h("div", { className: "boutons" },
          h("button", { className: "bouton discret", onclick: () => fermer(false) }, "Annuler"),
          bouton)));
    document.addEventListener("keydown", clavier, true);
    document.body.append(fond);
    bouton.focus();
  });
}

function demanderTexte(message, valeur, { oui = "Valider" } = {}) {
  return new Promise((resoudre) => {
    const fermer = (reponse) => { fond.remove(); resoudre(reponse); };
    const entree = h("input", { className: "entree", value: valeur || "",
      onkeydown: (e) => { if (e.key === "Enter") fermer(entree.value); if (e.key === "Escape") { e.stopPropagation(); fermer(null); } } });
    const fond = h("div", { className: "modale-fond" },
      h("div", { className: "modale", role: "dialog", "aria-modal": "true" },
        h("p", {}, message), entree, h("div", { style: { height: "18px" } }),
        h("div", { className: "boutons" },
          h("button", { className: "bouton discret", onclick: () => fermer(null) }, "Annuler"),
          h("button", { className: "bouton principal", onclick: () => fermer(entree.value) }, oui))));
    document.body.append(fond);
    entree.focus();
    entree.select();
  });
}

// --- Données ---------------------------------------------------------------

async function chargerEtat() {
  etat.statut = await api("GET", "/api/etat");
  etat.donnees = etat.statut.ouvert ? await api("GET", "/api/projet") : null;
  if (etat.statut.ouvert && !etat.schema) etat.schema = await api("GET", "/api/schema");
}

const mots = () => etat.donnees.mots_cles;
const motParId = (id) => mots().find((m) => m.id === id);
const enfantsDe = (id) => mots().filter((m) => m.parent_id === id);
const themes = () => mots().filter((m) => !m.parent_id || !motParId(m.parent_id));
const couleurDe = (m) => m.couleur || (m.parent_id && motParId(m.parent_id)?.couleur) || PALETTE[0];

function correspond(m) {
  if (!etat.filtre) return true;
  const f = sansAccents(etat.filtre);
  return [m.libelle, ...m.synonymes].some((t) => sansAccents(t).includes(f));
}

function prochaineCouleur() {
  const prises = new Set(themes().map((m) => m.couleur));
  return PALETTE.find((c) => !prises.has(c)) || PALETTE[themes().length % PALETTE.length];
}

async function modifierMot(id, changements) {
  await essayer(async () => {
    etat.donnees = await api("PATCH", `/api/mots-cles/${id}`, changements);
    rendre();
  });
}

async function creerMot(libelle, parentId) {
  libelle = libelle.trim();
  if (!libelle) return false;
  const corps = { libelle, parent_id: parentId };
  if (!parentId) corps.couleur = prochaineCouleur();
  const reponse = await essayer(() => api("POST", "/api/mots-cles", corps));
  if (!reponse) return false;
  etat.donnees = reponse;
  rendre();
  return reponse.cree;  // l'identifiant du nouveau mot-clé
}

// « ＋ mot-clé » : un bouton qui devient un champ. On tape : un mot-clé existant est proposé
// (accents et majuscules ne comptent pas, synonymes compris) ; sinon, Entrée le crée comme
// nouveau thème. `cle` distingue les champs d'une même page ; `surChoisi(id)` reçoit le mot-clé.
function ajoutMotCle(cle, surChoisi, libelle = "mot-clé") {
  if (etat.ajoutMot !== cle) {
    return h("button", { className: "pastille ajout-mot", title: "Ajouter un mot-clé existant ou en créer un nouveau",
      onclick: (ev) => { ev.stopPropagation(); etat.ajoutMot = cle; etat.focusApres = `ajout-mot-${cle}`; rendre(); } }, `＋ ${libelle}`);
  }
  const fermer = () => { if (etat.ajoutMot === cle) { etat.ajoutMot = null; rendre(); } };
  const valider = async (texte) => {
    texte = texte.trim();
    if (!texte) return fermer();
    const cherche = sansAccents(texte);
    const existant = mots().find((m) => [m.libelle, ...m.synonymes].some((x) => sansAccents(x) === cherche));
    const id = existant ? existant.id : await creerMot(texte, null);
    if (!id) return;
    etat.ajoutMot = null;
    if (!existant) toast(`Mot-clé « ${texte} » créé`);
    await surChoisi(id);
    rendre();
  };
  const idListe = `mots-connus-${cle}`;
  return h("span", { className: "ajout-mot-champ" },
    h("input", { id: `ajout-mot-${cle}`, className: "entree", list: idListe, placeholder: "Mot-clé, puis Entrée",
      "data-cle": `ajout-mot-${cle}`, "aria-label": "Mot-clé à ajouter",
      onkeydown: (ev) => {
        if (ev.key === "Enter") { ev.preventDefault(); ev.stopPropagation(); valider(ev.target.value); }
        if (ev.key === "Escape") { ev.stopPropagation(); fermer(); }
      },
      onblur: (ev) => { if (!ev.target.value.trim()) setTimeout(fermer, 150); } }),
    h("datalist", { id: idListe }, mots().map((m) => h("option", { value: m.libelle }))));
}

async function supprimerMot(id) {
  const mot = motParId(id);
  let reponse = await essayer(() => api("DELETE", `/api/mots-cles/${id}`));
  if (reponse && reponse.confirmation) {
    if (!(await demander(reponse.confirmation, { oui: "Supprimer", danger: true }))) return;
    reponse = await essayer(() => api("DELETE", `/api/mots-cles/${id}?confirme=1`));
  }
  if (!reponse) return;
  etat.donnees = reponse;
  etat.panneau = null;
  toast(`« ${mot.libelle} » supprimé`);
  rendre();
}

async function fusionner(absorberId, garderId) {
  const absorbe = motParId(absorberId), garde = motParId(garderId);
  const n = absorbe.nb_extraits;
  const message = `« ${absorbe.libelle} » va disparaître : ${n ? pluriel(n, "extrait") + " passeront" : "ses extraits passeront"} `
    + `sous « ${garde.libelle} », et « ${absorbe.libelle} » deviendra un de ses synonymes.`;
  if (!(await demander(message, { oui: "Fusionner" }))) return;
  const reponse = await essayer(() => api("POST", `/api/mots-cles/${garderId}/fusionner`, { absorber: absorberId }));
  if (!reponse) return;
  etat.donnees = reponse;
  etat.panneau = garderId;
  toast("Mots-clés fusionnés");
  rendre();
}

async function modifierProjet(changements) {
  await essayer(async () => {
    etat.donnees = await api("PATCH", "/api/projet", changements);
    toast("Enregistré");
    rendre();
  });
}

async function ouvrir(options) {
  await essayer(async () => {
    etat.statut = await api("POST", "/api/ouvrir", options);
    etat.donnees = etat.statut.ouvert ? await api("GET", "/api/projet") : null;
    if (etat.statut.ouvert && !etat.schema) etat.schema = await api("GET", "/api/schema");
    etat.conflitsMasques = false;
    if (etat.statut.ouvert) await chargerVue(); else rendre();
  });
}

async function fermerMemoire() {
  await essayer(async () => {
    await api("POST", "/api/fermer");
    etat.ferme = true;
    rendre();
  });
}

// --- Rendu -----------------------------------------------------------------

// Redessiner remplace les champs : on retient celui qui avait le focus (par sa
// clé data-cle) pour le rendre à l'utilisateur, avec la position du curseur.
function rendre() {
  const actif = document.activeElement;
  const cle = actif && actif.dataset ? actif.dataset.cle : null;
  const selection = !cle ? null : actif.isContentEditable ? curseurDans(actif)
    : "selectionStart" in actif ? [actif.selectionStart, actif.selectionEnd] : null;
  // Gras ou italique en attente (Ctrl+I puis pause) : le navigateur l'oublie quand le champ
  // est redessiné ; on le note pour le rétablir, sinon la suite de la frappe changerait de style.
  const styleSaisie = cle && actif.isContentEditable
    ? { bold: document.queryCommandState("bold"), italic: document.queryCommandState("italic") } : null;
  const defilements = [...document.querySelectorAll("[data-defilement]")].map((el) => [el.dataset.defilement, el.scrollTop]);
  const racine = document.getElementById("app");
  racine.replaceChildren(vuePrincipale());
  for (const [cle, haut] of defilements) {
    const el = document.querySelector(`[data-defilement="${cle}"]`);
    if (el) el.scrollTop = haut;
  }
  const dejaOuvert = document.querySelector(".panneau")?.dataset.id;
  document.querySelectorAll(".voile, .panneau").forEach((el) => el.remove());
  if (etat.panneau && etat.donnees && !etat.ferme && motParId(etat.panneau)) {
    const elements = panneauMot(motParId(etat.panneau));
    // N'animer l'ouverture qu'une fois, pas à chaque modification dans le panneau.
    if (dejaOuvert) elements.forEach((el) => { el.style.animation = "none"; });
    document.body.append(...elements);
  }
  if (etat.focusApres) {
    const el = document.querySelector(`[data-cle="${etat.focusApres}"]`);
    el?.focus();
    if (el?.isContentEditable) placerCurseur(el, [el.textContent.length, el.textContent.length]);  // à la fin du texte
    etat.focusApres = null;
  } else if (cle) {
    const el = document.querySelector(`[data-cle="${cle}"]`);
    if (el) {
      el.focus();
      if (selection && el.isContentEditable) {
        placerCurseur(el, selection);
        if (styleSaisie && selection[0] === selection[1]) {
          for (const [commande, voulu] of Object.entries(styleSaisie)) {
            if (document.queryCommandState(commande) !== voulu) document.execCommand(commande);
          }
        }
      }
      else if (selection && "setSelectionRange" in el) try { el.setSelectionRange(...selection); } catch (e) { /* champ sans curseur */ }
    }
  }
}

function vuePrincipale() {
  if (etat.ferme) return ecranFerme();
  if (!etat.statut.ouvert) return ecranAccueil();
  document.title = etat.donnees.projet.titre ? `${etat.donnees.projet.titre} — APAche` : "APAche";
  return h("div", { className: "cadre" }, barre(),
    h("main", { className: "contenu" + (etat.vue === "extraits" ? " large" : "") }, bandeauConflits(),
      etat.vue === "extraits" ? (grille.donnees ? vueGrille() : h("div"))
        : etat.vue === "bibliographie" ? (etat.bibliographie ? vueBibliographie() : h("div"))
        : etat.vue === "plan" ? (etat.plan ? vuePlan() : h("div"))
        : etat.vue === "sources" ? vueSources() : vueProjet()));
}

function rendreBarre() {
  const ancienne = document.querySelector(".barre");
  if (ancienne) ancienne.replaceWith(barre());
}

function barre() {
  const titre = etat.donnees.projet.titre;
  const nav = (id, libelle, icone, disponible) =>
    h("button", { className: "nav" + (etat.vue === id ? " actif" : ""), disabled: !disponible, icone,
      onclick: () => allerA(`#/${id}`) },
      libelle, !disponible && h("span", { className: "bientot" }, "bientôt"));
  const sombre = document.documentElement.dataset.theme === "dark"
    || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  return h("nav", { className: "barre" },
    h("div", { className: "marque" },
      h("div", { className: "nom" }, "APAche"),
      titre && h("div", { className: "sous" }, titre)),
    // D'abord la bibliothèque (ce qu'on garde de ses lectures), puis ce qui sert un travail précis.
    nav("sources", "Sources", "sources", true),
    nav("extraits", "Extraits", "grille", true),
    nav("plan", "Plan", "plan", true),
    nav("bibliographie", "Bibliographie", "biblio", true),
    nav("projet", "Projet", "projet", true),
    h("div", { className: "pied" },
      h("button", { className: "icone", title: sombre ? "Mode clair" : "Mode sombre", "aria-label": sombre ? "Mode clair" : "Mode sombre",
        icone: sombre ? "soleil" : "lune",
        onclick: () => {
          document.documentElement.dataset.theme = sombre ? "light" : "dark";
          try { localStorage.setItem("theme", document.documentElement.dataset.theme); } catch (e) { /* stockage indisponible */ }
          rendreBarre();
        } }),
      h("button", { className: "bouton discret petit", icone: "quitter", title: "Sauvegarder, libérer le mémoire pour l'autre PC et quitter",
        onclick: fermerMemoire }, "Fermer")));
}

function bandeauConflits() {
  const conflits = etat.statut.conflits;
  if (!conflits.length || etat.conflitsMasques) return null;
  return h("div", { className: "bandeau", icone: "alerte" },
    h("div", { className: "texte" },
      h("strong", {}, "La synchronisation a créé une copie en conflit"), "\n",
      `Fichier${conflits.length > 1 ? "s" : ""} : ${conflits.join(", ")}. Cela arrive quand le mémoire a été modifié sur les deux PC `
      + "avant la fin de la synchronisation. Ce que tu vois ici est la version principale ; l'autre copie contient peut-être "
      + "des modifications à reprendre. Rien n'a été supprimé."),
    h("button", { className: "icone fermer-bandeau", icone: "croix", title: "Masquer pour cette fois", "aria-label": "Masquer",
      onclick: () => { etat.conflitsMasques = true; rendre(); } }));
}

// --- Écran Projet ----------------------------------------------------------

function vueProjet() {
  const p = etat.donnees.projet;
  const champProjet = (cle, placeholder, classe) =>
    h("input", { className: "champ-texte " + (classe || ""), value: p[cle], placeholder, "data-cle": "projet-" + cle,
      "aria-label": placeholder,
      onchange: (e) => modifierProjet({ [cle]: e.target.value.trim() }),
      onkeydown: (e) => { if (e.key === "Enter") e.target.blur(); } });
  const info = (cle, label, placeholder) =>
    h("div", { className: "info" }, h("label", {}, label), champProjet(cle, placeholder));

  return h("div", {},
    champProjet("titre", "Titre du mémoire ou du travail (facultatif)", "titre-projet"),
    champProjet("sous_titre", "Sous-titre (facultatif)", "sous-titre-projet"),
    h("div", { className: "infos-projet" },
      info("auteur", "Auteur", "Ton nom"),
      info("promoteur", "Promoteur", "Nom du promoteur"),
      info("annee_academique", "Année académique", "2026-2027")),
    sectionMotsCles(),
    sectionReglages(),
    sectionConfidentialite(),
    sectionImport(),
    sectionImportBiblio(),
    sectionImportDossiers(),
    sectionDossier());
}

function sectionMotsCles() {
  const liste = themes().filter((t) => correspond(t) || enfantsDe(t.id).some(correspond));
  const recherche = h("label", { className: "recherche", icone: "loupe" },
    h("input", { placeholder: "Filtrer", value: etat.filtre, "data-cle": "filtre", "aria-label": "Filtrer les mots-clés",
      oninput: (e) => { etat.filtre = e.target.value; rendre(); },
      onkeydown: (e) => { if (e.key === "Escape") { etat.filtre = ""; e.target.blur(); rendre(); } } }),
    h("kbd", {}, "/"));
  const nouveau = h("button", { className: "bouton principal", icone: "plus",
    onclick: () => { etat.saisie = { parent: null }; rendre(); } }, "Nouveau thème");

  let corps;
  if (!mots().length && !etat.saisie) {
    corps = h("div", { className: "vide" },
      h("h3", {}, "Aucun mot-clé pour l'instant"),
      h("p", {}, "Commence par les grands thèmes qui t'intéressent. Tu pourras les découper en sous-thèmes ensuite."),
      h("button", { className: "bouton principal", icone: "plus", onclick: () => { etat.saisie = { parent: null }; rendre(); } },
        "Créer un premier thème"), " ", h("kbd", {}, "N"));
  } else {
    corps = h("div", { className: "themes" },
      etat.saisie && etat.saisie.parent === null && h("div", { className: "theme" }, saisieRapide(null)),
      liste.map(carteTheme),
      etat.filtre && !liste.length && h("p", { className: "aide" }, `Aucun mot-clé ne contient « ${etat.filtre} ».`));
  }
  return h("section", { className: "section" },
    h("div", { className: "section-tete" }, h("h2", {}, "Mots-clés"),
      h("div", { className: "actions" }, mots().length ? recherche : null, mots().length ? nouveau : null)),
    h("p", { className: "aide" }, "Les thèmes qui classent tes extraits. Clique sur un mot-clé pour le renommer, "
      + "changer sa couleur ou lui ajouter des synonymes."),
    mots().length ? mesureSuggestions() : null,
    corps);
}

// Ce que valent les suggestions sur les extraits déjà classés : dit
// franchement, pour savoir quand leur faire confiance et quels synonymes ajouter.
function mesureSuggestions() {
  const m = etat.mesure;
  const lancer = async () => {
    etat.mesure = { enCours: true };
    rendre();
    etat.mesure = await essayer(() => api("GET", "/api/mots-cles/mesure"));
    rendre();
  };
  let texte;
  if (!m) texte = "Les mots-clés et leurs synonymes servent aussi à proposer des mots-clés quand tu crées un extrait.";
  else if (m.enCours) texte = "Mesure en cours…";
  else if (!m.extraits || m.justes === null) texte = "Pas encore assez d'extraits classés pour mesurer les suggestions.";
  else texte = `Sur tes ${m.extraits} extraits classés, ${m.justes} % des mots-clés que l'outil proposerait sont justes, `
    + `et il retrouve ${m.retrouves} % de ceux que tu as posés. `
    + (m.retrouves < 40 ? "C'est peu : ajoute des synonymes (les mots que tes textes emploient vraiment) pour qu'il en trouve davantage."
      : m.justes < 50 ? "Beaucoup de fausses pistes : un synonyme trop général (« culture », « ville ») en est souvent la cause."
      : "Ses propositions sont fiables ; tu gardes toujours le dernier mot.");
  return h("div", { className: "mesure-suggestions" },
    h("span", {}, texte),
    !m?.enCours ? h("button", { className: "bouton discret petit", onclick: lancer }, m ? "Mesurer à nouveau" : "Mesurer les suggestions") : null);
}

function carteTheme(theme) {
  const enfants = enfantsDe(theme.id)
    .filter((m) => correspond(theme) || correspond(m))
    .sort((a, b) => a.libelle.localeCompare(b.libelle, "fr"));
  const ouvrirPanneau = () => { etat.panneau = theme.id; rendre(); };
  return h("div", { className: "theme" },
    h("div", { className: "ligne-mot" + (etat.panneau === theme.id ? " selectionne" : ""), style: { "--c": couleurDe(theme) },
      tabIndex: 0, role: "button", onclick: ouvrirPanneau,
      onkeydown: (e) => { if (e.key === "Enter" && e.target === e.currentTarget) ouvrirPanneau(); } },
      h("span", { className: "pastille-point" }),
      h("span", { className: "libelle" }, theme.libelle),
      theme.synonymes.length ? h("span", { className: "synonymes" }, "aussi : " + theme.synonymes.join(", ")) : null,
      h("span", { className: "compte" }, pluriel(theme.nb_extraits, "extrait")),
      h("span", { className: "survol" },
        h("button", { className: "bouton discret petit", icone: "plus", title: "Ajouter un sous-thème",
          onclick: (e) => { e.stopPropagation(); etat.saisie = { parent: theme.id }; rendre(); } }, "Sous-thème"))),
    h("div", { className: "sous-themes" },
      enfants.map((m) => h("button", {
        className: "pastille" + (etat.panneau === m.id ? " selectionne" : ""), style: { "--c": couleurDe(m) },
        title: m.synonymes.length ? "Synonymes : " + m.synonymes.join(", ") : "Modifier",
        onclick: () => { etat.panneau = m.id; rendre(); } },
        m.libelle, m.nb_extraits ? h("span", { className: "n" }, m.nb_extraits) : null)),
      etat.saisie && etat.saisie.parent === theme.id ? saisieRapide(theme.id) : null));
}

// Saisie enchaînée : Entrée crée et laisse le champ ouvert pour le suivant,
// parce qu'on crée souvent plusieurs mots-clés d'affilée.
function saisieRapide(parentId) {
  const entree = h("input", {
    placeholder: parentId ? "Nouveau sous-thème" : "Nom du thème", "data-cle": "saisie-" + (parentId || "theme"),
    "aria-label": parentId ? "Nouveau sous-thème" : "Nom du nouveau thème",
    onkeydown: async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (!entree.value.trim()) { etat.saisie = null; rendre(); return; }
        if (await creerMot(entree.value, parentId)) {
          const suivant = document.querySelector(`[data-cle="saisie-${parentId || "theme"}"]`);
          if (suivant) { suivant.value = ""; suivant.focus(); }
        }
      } else if (e.key === "Escape") {
        e.stopPropagation();
        etat.saisie = null; rendre();
      }
    },
    onblur: () => {
      // Laisser le temps à un clic ailleurs (autre bouton) d'agir avant de refermer.
      setTimeout(() => {
        if (etat.saisie && !entree.value.trim() && document.activeElement !== entree
            && !document.querySelector(`[data-cle="saisie-${parentId || "theme"}"]:focus`)) {
          etat.saisie = null; rendre();
        }
      }, 150);
    },
  });
  setTimeout(() => { if (document.activeElement === document.body) entree.focus(); });
  return h("div", { className: "saisie-rapide" },
    !parentId && h("span", { className: "pastille-point", style: { "--c": prochaineCouleur(), width: "10px", height: "10px", borderRadius: "50%", background: "var(--c)" } }),
    entree,
    h("span", { className: "indice" }, h("kbd", {}, "Entrée"), " créer · ", h("kbd", {}, "Échap"), " fermer"));
}

// --- Panneau d'édition d'un mot-clé -----------------------------------------

function panneauMot(mot) {
  const fermer = () => { etat.panneau = null; rendre(); };
  const aDesEnfants = enfantsDe(mot.id).length > 0;
  const estSousTheme = Boolean(mot.parent_id);

  const libelle = h("input", { className: "entree", value: mot.libelle, "data-cle": "p-libelle", "aria-label": "Nom",
    onchange: (e) => {
      if (!e.target.value.trim()) { e.target.value = mot.libelle; return; }
      modifierMot(mot.id, { libelle: e.target.value });
    },
    onkeydown: (e) => { if (e.key === "Enter") e.target.blur(); } });

  const nuancier = h("div", { className: "nuancier", role: "radiogroup", "aria-label": "Couleur" },
    estSousTheme && h("button", { title: "Comme le thème", "aria-label": "Comme le thème",
      className: mot.couleur ? "" : "actif",
      style: { "--c": motParId(mot.parent_id)?.couleur || PALETTE[0], backgroundImage: "linear-gradient(135deg, transparent 45%, var(--surface) 45%, var(--surface) 55%, transparent 55%)" },
      onclick: () => modifierMot(mot.id, { couleur: "" }) }),
    PALETTE.map((c) => h("button", { style: { "--c": c }, className: mot.couleur === c ? "actif" : "", "aria-label": c,
      onclick: () => modifierMot(mot.id, { couleur: c }) })));

  const parents = themes().filter((t) => t.id !== mot.id).sort((a, b) => a.libelle.localeCompare(b.libelle, "fr"));
  const rangement = h("select", { className: "entree", disabled: aDesEnfants, "aria-label": "Rangé sous",
    onchange: (e) => modifierMot(mot.id, { parent_id: e.target.value || null }) },
    h("option", { value: "", selected: !mot.parent_id }, "Aucun : c'est un thème principal"),
    parents.map((t) => h("option", { value: t.id, selected: mot.parent_id === t.id }, t.libelle)));

  const saisieSynonyme = h("input", { placeholder: mot.synonymes.length ? "" : "Ajouter un synonyme…", "data-cle": "p-synonyme",
    "aria-label": "Ajouter un synonyme",
    onkeydown: (e) => {
      const valeur = e.target.value.trim();
      if ((e.key === "Enter" || e.key === ",") && valeur) {
        e.preventDefault();
        modifierMot(mot.id, { synonymes: [...mot.synonymes, valeur] });
      } else if (e.key === "Backspace" && !e.target.value && mot.synonymes.length) {
        modifierMot(mot.id, { synonymes: mot.synonymes.slice(0, -1) });
      }
    } });
  const synonymes = h("div", { className: "jetons", onclick: () => saisieSynonyme.focus() },
    mot.synonymes.map((s, i) => h("span", { className: "jeton" }, s,
      h("button", { "aria-label": `Retirer ${s}`, title: "Retirer",
        onclick: () => modifierMot(mot.id, { synonymes: mot.synonymes.filter((_, j) => j !== i) }) }, "×"))),
    saisieSynonyme);

  const cibles = mots().filter((m) => m.id !== mot.id).sort((a, b) => a.libelle.localeCompare(b.libelle, "fr"));
  const cibleFusion = h("select", { className: "entree", "aria-label": "Fusionner dans" },
    h("option", { value: "" }, "Fusionner dans…"),
    cibles.map((m) => h("option", { value: m.id }, m.libelle)));

  const champ = (label, detail, ...contenu) =>
    h("div", { className: "champ" }, h("label", {}, label), ...contenu, detail && h("span", { className: "detail" }, detail));

  return [
    h("div", { className: "voile", onclick: fermer }),
    h("aside", { className: "panneau", role: "dialog", "aria-label": "Modifier le mot-clé", "data-id": mot.id },
      h("div", { className: "panneau-tete" },
        h("span", { className: "pastille", style: { "--c": couleurDe(mot), cursor: "default" } }, estSousTheme ? "Sous-thème" : "Thème"),
        h("button", { className: "icone", icone: "croix", title: "Fermer (Échap)", "aria-label": "Fermer", onclick: fermer })),
      h("div", { className: "panneau-corps" },
        champ("Nom", mot.nb_extraits ? `Utilisé par ${pluriel(mot.nb_extraits, "extrait")}. Le renommer ne les touche pas.` : null, libelle),
        champ("Synonymes", "D'autres façons de dire la même chose. Ils aideront plus tard l'outil à te proposer ce mot-clé tout seul.", synonymes),
        champ("Couleur", null, nuancier),
        champ("Rangé sous", aDesEnfants ? "Ce thème a des sous-thèmes : il reste un thème principal." : null, rangement)),
      h("div", { className: "panneau-pied" },
        h("div", { className: "rangee" }, cibleFusion,
          h("button", { className: "bouton", onclick: () => cibleFusion.value && fusionner(mot.id, cibleFusion.value) }, "Fusionner")),
        h("div", {}, h("button", { className: "bouton danger petit", onclick: () => supprimerMot(mot.id) }, "Supprimer ce mot-clé")))),
  ];
}

// --- Import du Google Doc d'extraits ---------------------------------------

async function analyserImport() {
  const imp = etat.import;
  imp.enCours = true;
  rendre();
  const apercu = await essayer(() => api("POST", "/api/import/apercu", { chemin: imp.chemin }));
  imp.enCours = false;
  if (apercu) {
    imp.apercu = apercu;
    imp.choix = new Set(apercu.onglets.filter((o) => o.propose).map((o) => o.titre));
    imp.rapport = null;
  }
  rendre();
}

async function lancerImport() {
  const imp = etat.import;
  imp.enCours = true;
  rendre();
  const reponse = await essayer(() => api("POST", "/api/import/extraits", { chemin: imp.chemin, onglets: [...imp.choix] }));
  imp.enCours = false;
  if (reponse) {
    const { rapport, ...donnees } = reponse;
    etat.donnees = donnees;
    imp.rapport = rapport;
    imp.apercu = null;
    const n = rapport.extraits_crees;
    toast(n ? `${pluriel(n, "extrait")} importé${n > 1 ? "s" : ""}` : "Rien de nouveau à importer");
  }
  rendre();
}

function sectionImport() {
  const imp = etat.import;
  const entree = h("input", { className: "entree", value: imp.chemin, "data-cle": "import-chemin",
    placeholder: "C:\\Users\\…\\Downloads\\extraits.docx", "aria-label": "Chemin du fichier Word à importer",
    oninput: (e) => { imp.chemin = e.target.value; },
    onkeydown: (e) => { if (e.key === "Enter" && !imp.enCours) analyserImport(); } });
  return h("section", { className: "section" },
    h("div", { className: "section-tete" }, h("h2", {}, "Importer des notes de lecture")),
    h("p", { className: "aide" }, "Si tu as déjà des extraits dans un Google Doc à onglets (un onglet par lecture, son titre en style "
      + "« Titre »), l'outil en fait des sources et des extraits. Dans Google Docs : Fichier → Télécharger → "
      + "Microsoft Word (.docx). Puis dans l'Explorateur, clic droit sur le fichier → « Copier en tant que chemin d'accès », "
      + "et colle-le ici. Le fichier n'est jamais modifié ; tu pourras réimporter une version plus récente sans créer de doublons."),
    h("div", { className: "rangee" }, entree,
      h("button", { className: "bouton" + (imp.apercu ? "" : " principal"), disabled: imp.enCours, onclick: analyserImport },
        imp.enCours && !imp.apercu ? "Lecture…" : "Analyser")),
    imp.apercu ? apercuImport() : imp.rapport ? resumeImport(imp.rapport) : null);
}

function apercuImport() {
  const imp = etat.import;
  const onglets = imp.apercu.onglets;
  const aImporter = onglets.filter((o) => imp.choix.has(o.titre)).reduce((n, o) => n + o.nouveaux, 0);
  const basculer = (titre) => { if (!imp.choix.delete(titre)) imp.choix.add(titre); rendre(); };
  const details = (o) => {
    if (o.deja_importe) return o.nouveaux ? `déjà importé · ${o.nouveaux} nouveau${o.nouveaux > 1 ? "x" : ""}` : "déjà importé, rien de nouveau";
    return [pluriel(o.extraits, "extrait"), o.integres && `${o.integres} intégré${o.integres > 1 ? "s" : ""}`,
      o.avec_page && `${o.avec_page} avec page`].filter(Boolean).join(" · ");
  };
  // Regrouper par thème, dans l'ordre du document.
  const groupes = new Map();
  for (const o of onglets) {
    const cle = o.theme ?? "";
    if (!groupes.has(cle)) groupes.set(cle, []);
    groupes.get(cle).push(o);
  }
  return h("div", { className: "import-apercu" },
    [...groupes].flatMap(([theme, liste]) => [
      h("h3", {}, theme ? `Thème « ${theme} »` : "Avant les notes de lecture"),
      ...liste.map((o) => {
        const coche = imp.choix.has(o.titre);
        return h("label", { className: "ligne-import" + (coche ? "" : " exclu"), title: o.exemple ? "Premier extrait : " + o.exemple : null },
          h("input", { type: "checkbox", checked: coche, onchange: () => basculer(o.titre) }),
          h("span", { className: "titre" }, o.titre),
          h("span", { className: "details" }, details(o)));
      }),
    ]),
    h("div", { className: "import-pied" },
      h("p", { className: "aide" }, "Chaque onglet coché devient une source, chaque thème un mot-clé. Les brouillons, réunions et liens "
        + "sont décochés : ce ne sont pas des lectures."),
      h("button", { className: "bouton discret", onclick: () => { imp.apercu = null; rendre(); } }, "Annuler"),
      h("button", { className: "bouton principal", disabled: imp.enCours || !aImporter, onclick: lancerImport },
        imp.enCours ? "Import…" : aImporter ? `Importer ${pluriel(aImporter, "extrait")}` : "Rien de nouveau")));
}

function resumeImport(r) {
  const s = (n) => (n > 1 ? "s" : "");
  const lignes = [
    `${pluriel(r.extraits_crees, "extrait")} importé${s(r.extraits_crees)}`
      + (r.sources_creees ? ` dans ${r.sources_creees} nouvelle${s(r.sources_creees)} source${s(r.sources_creees)}` : "")
      + (r.sources_completees ? `, ${pluriel(r.sources_completees, "source")} complétée${s(r.sources_completees)}` : "") + ".",
    r.extraits_deja_la && `${r.extraits_deja_la} déjà présent${s(r.extraits_deja_la)}, laissé${s(r.extraits_deja_la)} tel${s(r.extraits_deja_la)} quel${s(r.extraits_deja_la)}.`,
    r.integres && `${r.integres} marqué${s(r.integres)} « intégré » : barré${s(r.integres)} dans le Google Doc.`,
    r.a_verifier && `${r.a_verifier} barré${s(r.a_verifier)} en partie seulement : leur note le signale, vérifie la case « intégré ».`,
    r.sans_page && `${r.sans_page} sans page, rangé${s(r.sans_page)} en paraphrase. Pour une citation littérale, ajoute la page.`,
    r.mots_cles_crees.length && `Nouveaux thèmes : ${r.mots_cles_crees.join(", ")}.`,
    r.sources_creees && "Les sources n'ont que l'auteur et l'année lus dans le nom de l'onglet : leur référence est à compléter.",
  ].filter(Boolean);
  return h("div", { className: "bandeau info", icone: "coche", style: { marginTop: "18px" } },
    h("div", { className: "texte" }, h("strong", {}, "Import terminé"), "\n", lignes.join("\n")),
    h("button", { className: "icone fermer-bandeau", icone: "croix", title: "Masquer", "aria-label": "Masquer",
      onclick: () => { etat.import.rapport = null; rendre(); } }));
}

// --- Réglages de citation et dossier ----------------------------------------

function sectionReglages() {
  const r = etat.donnees.projet.reglages_apa;
  const enregistrer = (cle, valeur) => modifierProjet({ reglages_apa: { [cle]: valeur } });
  const texte = (cle, label, detail) => h("div", { className: "champ" },
    h("label", { htmlFor: "r-" + cle }, label),
    h("input", { id: "r-" + cle, className: "entree", value: r[cle], "data-cle": "r-" + cle,
      onchange: (e) => enregistrer(cle, e.target.value) }),
    detail && h("span", { className: "detail" }, detail));

  const ouvert = document.querySelector("details.repli")?.open;
  return h("section", { className: "section" },
    h("div", { className: "section-tete" }, h("h2", {}, "Citations")),
    h("p", { className: "aide" }, "Les petits mots que l'outil insère dans les citations et la bibliographie. "
      + "Les valeurs proposées suivent l'usage français de l'APA ; à vérifier avec le guide de ton université."),
    h("details", { className: "repli", open: ouvert },
      h("summary", {}, h("span", { className: "chevron", icone: "chevron" }), "Réglages de citation",
        h("span", { className: "resume" }, `Martin ${r.conjonction} Dubois, ${r.sans_date}, ${r.page} 45`)),
      h("div", { className: "grille-reglages" },
        h("div", { className: "champ" },
          h("label", {}, "Entre deux auteurs"),
          h("div", { className: "segments" },
            ["et", "&"].map((v) => h("button", { className: r.conjonction === v ? "actif" : "",
              onclick: () => modifierProjet({ reglages_apa: { conjonction: v } }) }, v))),
          h("span", { className: "detail" }, `(Martin ${r.conjonction} Dubois, 2020)`)),
        texte("sans_date", "Source sans date", `(Martin, ${r.sans_date})`),
        texte("cite_dans", "Auteur cité par un autre", `(Piaget, 1952, ${r.cite_dans} Martin, 2020)`),
        texte("page", "Une page", `(Martin, 2020, ${r.page} 45)`),
        texte("pages", "Plusieurs pages", `(Martin, 2020, ${r.pages} 45-47)`),
        texte("directeur", "Direction d'un ouvrage collectif", `Dubois, A. ${r.directeur}`),
        texte("consulte_le", "Date de consultation d'un site", `${r.consulte_le} 3 octobre 2026`))));
}

function sectionConfidentialite() {
  const active = etat.donnees.projet.recherche_en_ligne;
  return h("section", { className: "section" },
    h("div", { className: "section-tete" }, h("h2", {}, "Confidentialité")),
    h("p", { className: "aide" }, "L'outil fonctionne entièrement sur ce PC : tes sources et tes extraits ne sont envoyés nulle part. "
      + "Une seule exception, que tu choisis : compléter une référence depuis son DOI ou son ISBN. Seul cet identifiant part "
      + "alors vers CrossRef, Open Library ou la BnF, et seulement quand tu cliques « Compléter en ligne »."),
    h("div", { className: "chemin" },
      h("span", {}, h("strong", {}, active ? "Recherche en ligne activée" : "Recherche en ligne désactivée"),
        active ? " : un DOI ou un ISBN part quand tu cliques « Compléter en ligne »." : " : rien ne sort de ce PC."),
      h("button", { className: "bouton petit", onclick: () => modifierProjet({ recherche_en_ligne: !active }) },
        active ? "Désactiver" : "Activer")));
}

function sectionDossier() {
  return h("section", { className: "section" },
    h("div", { className: "section-tete" }, h("h2", {}, "Dossier de données")),
    h("p", { className: "aide" }, "L'endroit où l'outil range ta bibliothèque et ses sauvegardes. Il est propre à ce PC."),
    h("div", { className: "chemin" },
      h("code", {}, etat.statut.dossier),
      h("button", { className: "bouton petit", icone: "crayon", onclick: async () => {
        const nouveau = await demanderTexte("Chemin du nouveau dossier de données :", etat.statut.dossier, { oui: "Ouvrir" });
        if (nouveau && nouveau.trim() && nouveau.trim() !== etat.statut.dossier) ouvrir({ dossier: nouveau });
      } }, "Changer")));
}

// --- Écrans hors projet -----------------------------------------------------

function ecranAccueil() {
  const probleme = etat.statut.probleme;
  const entree = h("input", { className: "entree", value: probleme?.dossier || etat.statut.dossier || "",
    placeholder: "G:\\Mon Drive\\APAche", "data-cle": "accueil-dossier", "aria-label": "Dossier de données",
    onkeydown: (e) => { if (e.key === "Enter") ouvrir({ dossier: entree.value }); } });
  let bandeau = null;
  let boutons = [h("button", { className: "bouton principal", onclick: () => ouvrir({ dossier: entree.value }) }, "Ouvrir")];

  if (probleme?.type === "verrou") {
    bandeau = h("div", { className: "bandeau", icone: "alerte" }, h("div", { className: "texte" }, probleme.message));
    boutons = [
      h("button", { className: "bouton principal", onclick: () => ouvrir({ dossier: probleme.dossier }) }, "Réessayer"),
      h("button", { className: "bouton", onclick: async () => {
        if (await demander("Si le mémoire est vraiment ouvert sur l'autre PC, les modifications faites des deux côtés "
          + "risquent de s'écraser. Ouvrir quand même ?", { oui: "Ouvrir quand même", danger: true })) {
          ouvrir({ dossier: probleme.dossier, forcer: true });
        }
      } }, "Ouvrir quand même"),
    ];
  } else if (probleme?.type === "absent" && probleme.creable) {
    bandeau = h("div", { className: "bandeau", icone: "alerte" }, h("div", { className: "texte" }, probleme.message));
    boutons = [
      h("button", { className: "bouton principal", onclick: () => ouvrir({ dossier: entree.value, creer: true }) }, "Créer le dossier"),
      h("button", { className: "bouton", onclick: () => ouvrir({ dossier: entree.value }) }, "Ouvrir un autre chemin"),
    ];
  } else if (probleme) {
    bandeau = h("div", { className: "bandeau erreur", icone: "alerte" }, h("div", { className: "texte" }, probleme.message));
  }

  setTimeout(() => { if (!probleme || probleme.type !== "verrou") entree.focus(); });
  return h("div", { className: "accueil" },
    h("div", { className: "carte" },
      h("h1", {}, probleme?.type === "verrou" ? "Déjà ouvert sur un autre PC ?" : "Où ranger ta bibliothèque ?"),
      probleme?.type !== "verrou" && h("p", { className: "accroche" }, ACCROCHE),
      probleme?.type !== "verrou" && h("p", {}, "Choisis un dossier où APAche gardera tes sources, tes extraits et leurs "
        + "sauvegardes : ta bibliothèque de lectures, pour un mémoire ou pour plus tard. Pour travailler sur plusieurs PC, prends un dossier synchronisé (Google Drive, OneDrive, Dropbox…). "
        + "Dans l'Explorateur, clic droit sur le dossier → « Copier en tant que chemin d'accès », puis colle-le ici."),
      bandeau,
      probleme?.type !== "verrou" && entree,
      h("div", { className: "boutons" }, boutons)));
}

function ecranFerme() {
  document.title = "APAche fermé";
  return h("div", { className: "accueil" },
    h("div", { className: "carte" },
      h("h1", {}, "APAche est fermé"),
      h("p", {}, "La sauvegarde est faite et ta bibliothèque est libérée : tu peux l'ouvrir sur un autre PC dès que "
        + "ton dossier a fini de se synchroniser."),
      h("p", {}, "Tu peux fermer cet onglet. Pour revenir, relance APAche."),));
}

// --- Raccourcis clavier ------------------------------------------------------

document.addEventListener("keydown", (e) => {
  if (raccourciGrille(e) || raccourciSources(e)) return;
  const cible = e.target;
  const enSaisie = cible.matches("input, textarea, select, [contenteditable]");
  if (e.key === "Escape") {
    if (etat.panneau) { etat.panneau = null; rendre(); }
    else if (etat.saisie) { etat.saisie = null; rendre(); }
    return;
  }
  if (enSaisie || e.altKey || e.metaKey || !etat.donnees || etat.ferme || etat.vue !== "projet"
      || document.querySelector(".modale-fond")) return;
  if ((e.key === "k" && e.ctrlKey) || (e.key === "/" && !e.ctrlKey)) {
    e.preventDefault();
    document.querySelector('[data-cle="filtre"]')?.focus();
  } else if (e.key.toLowerCase() === "n" && !e.ctrlKey) {
    e.preventDefault();
    etat.panneau = null;
    etat.saisie = { parent: null };
    rendre();
  }
});

(async () => {
  try {
    await chargerEtat();
  } catch (e) {
    document.getElementById("app").replaceChildren(h("div", { className: "accueil" },
      h("div", { className: "carte" }, h("h1", {}, "L'outil ne répond pas"), h("p", {}, e.message))));
    return;
  }
  if (etat.statut.ouvert) await chargerVue(); else rendre();
})();
