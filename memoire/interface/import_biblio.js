"use strict";

// Import d'une bibliographie existante : une
// référence à la fois ; l'utilisateur fusionne avec une source existante, crée
// une source ou passe. Chargé avant app.js, dont il utilise les outils.

const biblio = { chemin: "", apercu: null, position: 0, enCours: false, faits: new Map() };

async function analyserBiblio() {
  biblio.enCours = true;
  rendre();
  const apercu = await essayer(() => api("POST", "/api/import/bibliographie/apercu", { chemin: biblio.chemin }));
  biblio.enCours = false;
  if (apercu) {
    biblio.apercu = apercu;
    const premiere = apercu.references.findIndex((r) => !r.deja);
    biblio.position = premiere >= 0 ? premiere : apercu.references.length;  // tout est déjà là : le résumé
  }
  rendre();
}

async function deciderBiblio(ref, action, sourceId) {
  biblio.enCours = true;
  rendre();
  const reponse = await essayer(() => api("POST", "/api/import/bibliographie/appliquer",
    { chemin: biblio.chemin, empreinte: ref.empreinte, action, source_id: sourceId }));
  biblio.enCours = false;
  if (!reponse) return;
  biblio.apercu = { document: reponse.document, references: reponse.references };
  biblio.faits.set(ref.empreinte, { action, source_id: reponse.source_id });
  toast(action === "creer" ? "Source créée" : "Référence versée dans la source");
  suivanteBiblio();
}

function suivanteBiblio() {
  const refs = biblio.apercu.references;
  const reste = refs.findIndex((r, i) => i > biblio.position && !r.deja && !biblio.faits.has(r.empreinte));
  const avant = refs.findIndex((r) => !r.deja && !biblio.faits.has(r.empreinte));
  biblio.position = reste >= 0 ? reste : avant >= 0 ? avant : refs.length;  // refs.length : terminé
  rendre();
}

function sectionImportBiblio() {
  const entree = h("input", { className: "entree", value: biblio.chemin, "data-cle": "biblio-chemin",
    placeholder: "C:\\Users\\…\\Downloads\\Biblio.docx", "aria-label": "Chemin de la bibliographie (.docx)",
    oninput: (e) => { biblio.chemin = e.target.value; },
    onkeydown: (e) => { if (e.key === "Enter" && !biblio.enCours) analyserBiblio(); } });
  return h("section", { className: "section" },
    h("div", { className: "section-tete" }, h("h2", {}, "Importer une bibliographie existante")),
    h("p", { className: "aide" }, "Une liste de références APA déjà utilisée (une première partie, un travail préparatoire…), en "
      + "Word (.docx), une par paragraphe. L'outil propose les champs de chaque référence et la source correspondante parmi "
      + "celles déjà là ; tu décides une par une. Tout ce qui est importé est marqué « déjà citée »."),
    h("div", { className: "rangee" }, entree,
      h("button", { className: "bouton" + (biblio.apercu ? "" : " principal"), disabled: biblio.enCours, onclick: analyserBiblio },
        biblio.enCours && !biblio.apercu ? "Lecture…" : "Analyser")),
    biblio.apercu ? (biblio.position >= biblio.apercu.references.length ? resumeBiblio() : carteBiblio()) : null);
}

function champsProposes(p) {
  const type = typeDe(p.type);
  const personnes = (liste) => liste.map((a) => a.organisation || [a.nom, a.prenom].filter(Boolean).join(", ")).join(" · ");
  const lignes = [["Type", p.libelle_type], ["Auteurs", personnes(p.auteurs)], ["Année", p.annee], ["Titre", p.titre]];
  for (const c of type.champs) {
    const v = p.champs[c.cle];
    if (v) lignes.push([c.libelle.split(" (")[0].replace(/ \?$/, ""), Array.isArray(v) ? personnes(v) : v === true ? "oui" : v]);
  }
  return h("dl", { className: "champs-proposes" },
    lignes.filter(([, v]) => v).flatMap(([cle, v]) => [h("dt", {}, cle), h("dd", {}, v)]));
}

function carteBiblio() {
  const refs = biblio.apercu.references;
  const ref = refs[biblio.position];
  const traitees = refs.filter((r) => r.deja || biblio.faits.has(r.empreinte)).length;
  const aller = (pas) => { biblio.position = Math.min(refs.length - 1, Math.max(0, biblio.position + pas)); rendre(); };
  const notes = [...ref.a_verifier, ...ref.a_completer.map((m) => `À compléter : ${m}`)];

  let decisions;
  if (ref.deja) {
    decisions = h("div", { className: "decisions" },
      h("p", { className: "aide" }, "Déjà importée."),
      h("button", { className: "bouton", onclick: () => allerA(`#/sources/${ref.deja.id}`) }, "Ouvrir la fiche"),
      h("button", { className: "bouton principal", onclick: suivanteBiblio }, "Suivante"));
  } else {
    decisions = h("div", { className: "decisions" },
      ref.candidats.length
        ? h("p", { className: "question" }, ref.candidats.length > 1 ? "Est-ce l'une de ces sources ?" : "Est-ce cette source ?")
        : h("p", { className: "question" }, "Aucune source existante ne correspond."),
      ref.candidats.map((c, i) => h("button", { className: "bouton candidat" + (i === 0 ? " principal" : ""), disabled: biblio.enCours,
        onclick: () => deciderBiblio(ref, "fusionner", c.id) },
        h("span", {}, `Oui : ${c.etiquette}`),
        h("span", { className: "detail" }, [c.onglet && `onglet « ${c.onglet} »`, pluriel(c.nb_extraits, "extrait")].filter(Boolean).join(" · ")))),
      h("div", { className: "rangee" },
        h("button", { className: "bouton" + (ref.candidats.length ? "" : " principal"), disabled: biblio.enCours,
          onclick: () => deciderBiblio(ref, "creer") }, ref.candidats.length ? "Non, créer une nouvelle source" : "Créer la source"),
        h("button", { className: "bouton discret", onclick: suivanteBiblio }, "Passer")));
  }

  return h("div", { className: "carte-biblio" },
    h("div", { className: "tete-biblio" },
      h("span", { className: "position" }, `Référence ${biblio.position + 1} sur ${refs.length}`),
      ref.section && h("span", { className: "puce discrete" }, ref.section),
      h("span", { className: "compte" }, `${traitees} traitée${traitees > 1 ? "s" : ""}`),
      h("button", { className: "icone", title: "Précédente", "aria-label": "Précédente", disabled: biblio.position === 0,
        onclick: () => aller(-1) }, "‹"),
      h("button", { className: "icone", title: "Suivante", "aria-label": "Suivante", disabled: biblio.position === refs.length - 1,
        onclick: () => aller(1) }, "›")),
    h("div", { className: "etiquette" }, "Dans ton fichier"),
    htmlServeur("p", { className: "notice avant" }, { html: ref.original }),
    h("div", { className: "etiquette" }, "Ce que l'outil en comprend"),
    ref.reference ? htmlServeur("p", { className: "notice" }, ref.reference) : null,
    champsProposes(ref.proposition),
    notes.length ? h("ul", { className: "notes-biblio" }, notes.map((n) => h("li", {}, n))) : null,
    decisions,
    h("p", { className: "aide petite" }, "Une erreur dans les champs ? Importe quand même : tout se corrige ensuite dans la fiche de la source."));
}

// « Pinel et Vidal (2017) » : la façon courte de nommer une référence.
function libelleBiblio(p) {
  const noms = p.auteurs.map((a) => a.organisation || a.nom);
  const qui = noms.length > 2 ? `${noms[0]} et al.` : noms.join(" et ") || p.titre;
  return `${qui} (${p.annee || "s. d."})`;
}

function resumeBiblio() {
  const refs = biblio.apercu.references;
  const lignes = refs.map((r) => {
    const fait = biblio.faits.get(r.empreinte);
    const id = fait?.source_id || r.deja?.id;
    const statut = fait ? (fait.action === "creer" ? "créée" : "fusionnée") : r.deja ? "déjà là" : "passée";
    return h("li", {},
      h("span", { className: "puce" + (id ? "" : " discrete") }, statut),
      id ? h("a", { href: `#/sources/${id}` }, libelleBiblio(r.proposition)) : h("span", {}, libelleBiblio(r.proposition)),
      r.a_verifier.length ? h("span", { className: "puce alerte", title: r.a_verifier.join("\n") }, "à vérifier") : null);
  });
  const passees = refs.filter((r) => !r.deja && !biblio.faits.has(r.empreinte)).length;
  return h("div", { className: "carte-biblio" },
    h("p", {}, h("strong", {}, "Bibliographie importée. "),
      passees ? `${pluriel(passees, "référence")} passée${passees > 1 ? "s" : ""} : relance l'analyse pour y revenir.` : ""),
    h("ul", { className: "resume-biblio" }, lignes));
}
