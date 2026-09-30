"use strict";

// Bibliographie finale : les sources réellement citées, en une liste (APA)
// ou en trois parties (par ex. Guide du Master de l'ULB), prêtes à coller d'un seul bloc.
// Chargé avant app.js, dont il utilise les outils.

async function chargerBibliographie() {
  etat.bibliographie = await api("GET", "/api/bibliographie");
}

function vueBibliographie() {
  const b = etat.bibliographie;
  const total = b.sections.reduce((n, s) => n + s.references.length, 0);
  const incompletes = b.sections.flatMap((s) => s.references.filter((r) => r.manques.length));

  const tete = h("div", { className: "section-tete tete-page" },
    h("h1", {}, "Bibliographie"),
    h("span", { className: "compte-page" }, pluriel(total, "référence")),
    total ? h("div", { className: "actions" },
      h("button", { className: "bouton principal", onclick: () => copier(b.copie, "Bibliographie copiée : colle-la dans Google Docs") },
        "Copier toute la bibliographie")) : null);

  if (!total) {
    return h("div", {}, tete, h("div", { className: "vide" },
      h("h3", {}, "Aucune source citée pour l'instant"),
      h("p", {}, "Une source entre dans la bibliographie quand un de ses extraits est coché « intégré », "
        + "ou quand elle est marquée « déjà citée »."),
      h("button", { className: "bouton", onclick: () => allerA("#/extraits") }, "Aller aux extraits")));
  }

  return h("div", { className: "bibliographie" },
    tete,
    h("p", { className: "aide" }, "Seules les sources réellement citées y figurent : au moins un extrait intégré, ou marquée "
      + "« déjà citée ». Ni les entretiens ni les auteurs cités de seconde main."),
    choixDecoupage(b.decoupage),
    incompletes.length ? h("div", { className: "bandeau", icone: "alerte" }, h("div", { className: "texte" },
      h("strong", {}, `${pluriel(incompletes.length, "référence")} à compléter`), "\n",
      incompletes.flatMap((r, i) => [i ? " · " : "", h("a", { href: `#/sources/${r.id}` }, r.etiquette),
        ` (${r.manques.map((m) => m.split(" (")[0].toLowerCase()).join(", ")})`]))) : null,
    b.sections.map((s) => h("section", { className: "partie-biblio" },
      h("div", { className: "tete-partie" },
        h("h2", {}, s.titre),
        h("span", { className: "compte" }, String(s.references.length)),
        h("button", { className: "bouton discret petit", onclick: () => copier(s.copie, `« ${s.titre} » copiée`) }, "Copier cette partie")),
      h("ol", { className: "notices" }, s.references.map((r) => h("li", { className: r.manques.length ? "incomplete" : "" },
        htmlServeur("p", { className: "notice" }, r),
        h("div", { className: "meta-notice" },
          h("span", {}, r.raison),
          r.manques.length ? h("span", { className: "puce alerte" }, "à compléter : " + r.manques.map((m) => m.split(" (")[0].toLowerCase()).join(", ")) : null,
          h("a", { href: `#/sources/${r.id}` }, "Ouvrir la fiche"),
          h("button", { className: "bouton discret petit", onclick: () => copier(r, "Référence copiée") }, "Copier")))))))
    ,
    b.non_incluses.length ? h("details", { className: "non-incluses" },
      h("summary", {}, `Lues mais pas encore citées (${b.non_incluses.length})`),
      h("p", { className: "aide" }, "Elles entreront d'elles-mêmes dans la bibliographie dès qu'un de leurs extraits sera coché « intégré »."),
      h("ul", {}, b.non_incluses.map((s) => h("li", {}, h("a", { href: `#/sources/${s.id}` }, s.etiquette),
        h("span", { className: "compte" }, ` · ${pluriel(s.nb_extraits, "extrait")}`))))) : null,
    sectionExport());
}

// Une seule liste, comme le veut l'APA, ou trois parties si ta formation le demande.
function choixDecoupage(actuel) {
  const choisir = async (valeur) => {
    if (valeur === actuel) return;
    await modifierProjet({ bibliographie: valeur });
    await chargerBibliographie();
    rendre();
  };
  return h("div", { className: "rangee choix-decoupage" },
    h("span", { className: "indice" }, "Présentation :"),
    h("div", { className: "segments", role: "radiogroup", "aria-label": "Présentation de la bibliographie" },
      h("button", { className: actuel === "une_liste" ? "actif" : "", onclick: () => choisir("une_liste"),
        title: "Toutes les références en une liste, dans l'ordre alphabétique (norme APA)" }, "Une seule liste"),
      h("button", { className: actuel === "trois_parties" ? "actif" : "", onclick: () => choisir("trois_parties"),
        title: "Références scientifiques, sources non scientifiques, sitographie (par ex. Guide du Master de l'ULB)" },
        "Trois parties")));
}

// Export RIS / BibTeX : une porte de sortie vers Zotero, Word, LaTeX… Le fichier est
// produit sur ce PC et enregistré par le navigateur, dans « Téléchargements ».
let exportToutes = false;

function sectionExport() {
  const sources = exportToutes ? "toutes" : "citees";
  const lien = (format, libelle) => h("a", { className: "bouton petit", href: `/api/export?format=${format}&sources=${sources}`,
    download: "" }, libelle);
  return h("section", { className: "export-biblio" },
    h("h2", {}, "Exporter vers un autre logiciel"),
    h("p", { className: "aide" }, "RIS pour Zotero, Mendeley, EndNote ou Word ; BibTeX pour LaTeX ou JabRef. "
      + "Le fichier arrive dans tes Téléchargements."),
    h("div", { className: "rangee" },
      h("div", { className: "segments" },
        h("button", { className: exportToutes ? "" : "actif", onclick: () => { exportToutes = false; rendre(); } }, "Sources citées"),
        h("button", { className: exportToutes ? "actif" : "", onclick: () => { exportToutes = true; rendre(); } }, "Toutes les sources")),
      lien("ris", "Exporter en RIS"),
      lien("bibtex", "Exporter en BibTeX")));
}
