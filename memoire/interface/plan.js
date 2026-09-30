"use strict";

// Plan du mémoire : chapitres et sections, chacun lié à des
// mots-clés ; choisir une partie montre ses extraits, ceux à intégrer d'abord.
// C'est le chemin « j'écris le chapitre 2 → je trouve les bons extraits ».
// Chargé avant app.js, dont il utilise les outils.

async function chargerPlan() {
  etat.plan = await api("GET", "/api/plan");
  const encore = etat.plan.sections.some((s) => s.id === etat.sectionChoisie);
  if (!encore) etat.sectionChoisie = etat.plan.sections[0]?.id || null;
  etat.sectionVue = etat.sectionChoisie ? await api("GET", `/api/plan/${etat.sectionChoisie}`) : null;
}

async function choisirSection(id) {
  etat.sectionChoisie = id;
  etat.renommer = null;
  const vue = await essayer(() => api("GET", `/api/plan/${id}`));
  if (vue) etat.sectionVue = vue;
  rendre();
}

// Toute modification du plan renvoie le plan entier ; la partie ouverte est relue
// (ses extraits dépendent de ses mots-clés).
async function changerPlan(appel, message) {
  const reponse = await essayer(appel);
  if (!reponse) return null;
  if (reponse.confirmation) return reponse;
  etat.plan = { sections: reponse.sections };
  if (reponse.cree) etat.sectionChoisie = reponse.cree;
  if (!etat.plan.sections.some((s) => s.id === etat.sectionChoisie)) etat.sectionChoisie = etat.plan.sections[0]?.id || null;
  etat.sectionVue = etat.sectionChoisie ? await essayer(() => api("GET", `/api/plan/${etat.sectionChoisie}`)) : null;
  if (message) toast(message);
  rendre();
  return reponse;
}

function ajouterPartie(titre, niveau, apres) {
  titre = titre.trim();
  if (!titre) return;
  changerPlan(() => api("POST", "/api/plan", { titre, niveau, ...(apres ? { apres } : {}) }));
}

async function supprimerPartie(s) {
  let reponse = await changerPlan(() => api("DELETE", `/api/plan/${s.id}`));
  if (reponse?.confirmation) {
    if (!(await demander(reponse.confirmation, { oui: "Supprimer", danger: true }))) return;
    reponse = await changerPlan(() => api("DELETE", `/api/plan/${s.id}?confirme=1`), "Partie supprimée");
  } else if (reponse) {
    toast("Partie supprimée");
  }
}

function vuePlan() {
  const sections = etat.plan.sections;
  const saisie = (niveau, apres, placeholder, cle) => h("input", { className: "entree saisie-partie", placeholder, "data-cle": cle,
    "aria-label": placeholder,
    onkeydown: (e) => {
      if (e.key === "Enter") { e.preventDefault(); etat.focusApres = cle; ajouterPartie(e.target.value, niveau, apres); }
    } });

  if (!sections.length) {
    return h("div", {},
      h("div", { className: "section-tete tete-page" }, h("h1", {}, "Plan")),
      h("div", { className: "vide" },
        h("h3", {}, "Ton plan est vide"),
        h("p", {}, "Écris tes chapitres, puis relie chacun aux mots-clés qui le nourrissent : l'outil te montrera, "
          + "pour chaque partie, les extraits qui restent à intégrer."),
        saisie(1, null, "Titre du premier chapitre, puis Entrée", "plan-premier")));
  }

  const choisie = sections.find((s) => s.id === etat.sectionChoisie);
  return h("div", { className: "plan" },
    h("div", { className: "section-tete tete-page" },
      h("h1", {}, "Plan"),
      h("span", { className: "compte-page" }, pluriel(sections.filter((s) => s.niveau === 1).length, "chapitre"))),
    h("div", { className: "plan-colonnes" },
      h("nav", { className: "plan-liste", "aria-label": "Parties du plan" },
        sections.map((s, i) => lignePartie(s, i, sections)),
        h("div", { className: "plan-ajout" },
          saisie(1, null, "Nouveau chapitre…", "plan-nouveau-chapitre"),
          choisie ? saisie(2, choisie.id, `Sous-section après ${choisie.numero}…`, "plan-nouvelle-section") : null)),
      h("div", { className: "plan-detail" }, choisie && etat.sectionVue ? detailPartie(choisie) : null)));
}

function lignePartie(s, i, sections) {
  const choisie = s.id === etat.sectionChoisie;
  const titre = etat.renommer === s.id
    ? h("input", { className: "entree renommer", value: s.titre, "data-cle": `renommer-${s.id}`, "aria-label": "Titre",
      onkeydown: (e) => {
        if (e.key === "Enter") e.target.blur();
        if (e.key === "Escape") { e.stopPropagation(); etat.renommer = null; rendre(); }
      },
      onblur: (e) => {
        etat.renommer = null;
        if (e.target.value.trim() && e.target.value.trim() !== s.titre) {
          changerPlan(() => api("PATCH", `/api/plan/${s.id}`, { titre: e.target.value }));
        } else rendre();
      } })
    : h("span", { className: "titre-partie" }, s.titre);
  return h("div", { className: "partie" + (choisie ? " choisie" : "") + (s.niveau === 2 ? " sous" : "") },
    h("button", { className: "tete-ligne", onclick: () => choisirSection(s.id), "aria-current": choisie ? "true" : null },
      h("span", { className: "numero" }, s.numero),
      titre,
      h("span", { className: "compte" }, s.nb_a_integrer ? `${s.nb_a_integrer} à intégrer` : s.nb_extraits ? "tout intégré" : "")),
    choisie ? h("div", { className: "outils-partie" },
      h("button", { className: "bouton discret petit", title: "Monter", "aria-label": "Monter", disabled: i === 0,
        onclick: () => changerPlan(() => api("POST", `/api/plan/${s.id}/deplacer`, { sens: "haut" })) }, "↑"),
      h("button", { className: "bouton discret petit", title: "Descendre", "aria-label": "Descendre", disabled: i === sections.length - 1,
        onclick: () => changerPlan(() => api("POST", `/api/plan/${s.id}/deplacer`, { sens: "bas" })) }, "↓"),
      h("button", { className: "bouton discret petit", onclick: () => changerPlan(() => api("PATCH", `/api/plan/${s.id}`, { niveau: s.niveau === 1 ? 2 : 1 })) },
        s.niveau === 1 ? "En section" : "En chapitre"),
      h("button", { className: "bouton discret petit", icone: "crayon",
        onclick: () => { etat.renommer = s.id; etat.focusApres = `renommer-${s.id}`; rendre(); } }, "Renommer"),
      h("button", { className: "bouton discret petit danger", onclick: () => supprimerPartie(s) }, "Supprimer")) : null);
}

function motsDePartie(s) {
  const autres = [];
  for (const t of themes().sort((a, b) => a.libelle.localeCompare(b.libelle, "fr"))) {
    autres.push(t, ...enfantsDe(t.id).sort((a, b) => a.libelle.localeCompare(b.libelle, "fr")));
  }
  const enregistrer = (mots) => changerPlan(() => api("PATCH", `/api/plan/${s.id}`, { mots_cles: mots }));
  return h("div", { className: "mots-partie" },
    s.mots_cles.map(motParId).filter(Boolean).map((m) => h("span", { className: "pastille", style: { "--c": couleurDe(m), cursor: "default" } },
      m.libelle,
      h("button", { className: "retirer-mot", "aria-label": `Retirer ${m.libelle}`, title: "Retirer",
        onclick: () => enregistrer(s.mots_cles.filter((id) => id !== m.id)) }, "×"))),
    h("select", { className: "entree choix", "aria-label": "Relier un mot-clé", "data-cle": `mots-partie-${s.id}`,
      onchange: (e) => { if (e.target.value) enregistrer([...s.mots_cles, e.target.value]); } },
      h("option", { value: "" }, s.mots_cles.length ? "+ mot-clé" : "Relier des mots-clés…"),
      autres.filter((m) => !s.mots_cles.includes(m.id)).map((m) => h("option", { value: m.id }, (m.parent_id ? "   " : "") + m.libelle))));
}

async function basculerIntegrePlan(e) {
  const vue = await essayer(() => api("PATCH", `/api/extraits/${e.id}`, { integre: !e.integre }));
  if (!vue) return;
  await changerPlan(async () => api("GET", "/api/plan"));
}

async function retirerDeLaPartie(e) {
  const vue = await essayer(() => api("PATCH", `/api/extraits/${e.id}`, { section_plan: null }));
  if (vue) await changerPlan(async () => api("GET", "/api/plan"), "Extrait retiré de cette partie");
}

function detailPartie(s) {
  const v = etat.sectionVue;
  const aIntegrer = v.extraits.filter((e) => !e.integre).length;
  return h("section", {},
    h("div", { className: "tete-partie-detail" },
      h("h2", {}, h("span", { className: "numero" }, s.numero), " ", s.titre),
      h("span", { className: "compte-page" }, v.extraits.length
        ? `${pluriel(v.extraits.length, "extrait")} · ${aIntegrer} à intégrer` : "")),
    motsDePartie(s),
    v.extraits.length
      ? h("div", { className: "liste-extraits" }, v.extraits.map((e, i) => [
        i > 0 && e.integre && !v.extraits[i - 1].integre ? h("div", { className: "separateur" }, "Déjà intégrés") : null,
        carteGrille(e, true, null, { sources: v.sources, surIntegre: basculerIntegrePlan,
          extra: e.a_la_main ? h("span", { className: "puce discrete a-la-main" }, "rangé ici",
            h("button", { className: "retirer-mot", title: "Retirer de cette partie", "aria-label": "Retirer de cette partie",
              onclick: () => retirerDeLaPartie(e) }, "×")) : null }),
      ]).flat())
      : h("div", { className: "vide petit" },
        h("p", {}, s.mots_cles.length
          ? "Aucun extrait ne porte ces mots-clés pour l'instant."
          : "Relie des mots-clés à cette partie : ses extraits apparaîtront ici. Tu peux aussi ranger un extrait "
            + "à la main, depuis son éditeur (« Partie du plan »).")));
}
