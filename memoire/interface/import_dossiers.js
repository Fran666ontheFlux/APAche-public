"use strict";

// Import des PDF des dossiers « à lire » et « lus » (par ex. « Articles à lire », « Articles LUS »)
// : un fichier à la fois ; le joindre à une source, en créer une,
// ou passer. Les fichiers sont copiés, jamais déplacés ni renommés.
// Chargé avant app.js, dont il utilise les outils.

const drive = { chemin: "", apercu: null, position: 0, enCours: false, faits: new Map() };
const LIBELLES_STATUT = { a_lire: "à lire", lu: "lu" };

async function analyserDossiers() {
  drive.enCours = true;
  rendre();
  const apercu = await essayer(() => api("POST", "/api/import/dossiers/apercu", { chemin: drive.chemin }));
  drive.enCours = false;
  if (apercu) {
    drive.apercu = apercu;
    const premier = apercu.fichiers.findIndex((f) => !f.deja);
    drive.position = premier >= 0 ? premier : apercu.fichiers.length;
  }
  rendre();
}

async function deciderDossier(f, action, sourceId) {
  drive.enCours = true;
  rendre();
  const reponse = await essayer(() => api("POST", "/api/import/dossiers/appliquer",
    { chemin: drive.chemin, empreinte: f.empreinte, action, source_id: sourceId }));
  drive.enCours = false;
  if (!reponse) return;
  drive.faits.set(f.empreinte, { action, source_id: reponse.source_id });
  toast(action === "creer" ? "Source créée, fichier joint" : "Fichier joint à la source");
  // Une source qui vient de recevoir un fichier n'est plus candidate pour les suivants.
  if (action === "joindre") {
    for (const autre of drive.apercu.fichiers) autre.candidats = autre.candidats.filter((c) => c.id !== sourceId);
  }
  suivantDossier();
}

function suivantDossier() {
  const liste = drive.apercu.fichiers;
  const libre = (f) => !f.deja && !drive.faits.has(f.empreinte);
  const apres = liste.findIndex((f, i) => i > drive.position && libre(f));
  const avant = liste.findIndex(libre);
  drive.position = apres >= 0 ? apres : avant >= 0 ? avant : liste.length;
  rendre();
}

function sectionImportDossiers() {
  const entree = h("input", { className: "entree", value: drive.chemin, "data-cle": "drive-chemin",
    placeholder: "G:\\Mon Drive\\Mémoire", "aria-label": "Chemin du dossier qui contient tes PDF",
    oninput: (e) => { drive.chemin = e.target.value; },
    onkeydown: (e) => { if (e.key === "Enter" && !drive.enCours) analyserDossiers(); } });
  return h("section", { className: "section" },
    h("div", { className: "section-tete" }, h("h2", {}, "Importer tes dossiers de PDF")),
    h("p", { className: "aide" }, "Le dossier qui contient un dossier « à lire » et un dossier « lus » (par ex. « Articles à lire » "
      + "et « Articles lus »), ou directement l'un des deux. "
      + "Chaque PDF devient une source, ou rejoint celle qui existe déjà, avec le statut de son dossier. Tes fichiers sont copiés "
      + "dans le dossier de données : jamais déplacés ni renommés. « Données/Entretiens » et les autres dossiers sont laissés de côté."),
    h("div", { className: "rangee" }, entree,
      h("button", { className: "bouton" + (drive.apercu ? "" : " principal"), disabled: drive.enCours, onclick: analyserDossiers },
        drive.enCours && !drive.apercu ? "Lecture des fichiers…" : "Analyser")),
    drive.apercu ? (drive.position >= drive.apercu.fichiers.length ? resumeDossiers() : carteDossier()) : null);
}

function carteDossier() {
  const liste = drive.apercu.fichiers;
  const f = liste[drive.position];
  const p = f.proposition;
  const traites = liste.filter((x) => x.deja || drive.faits.has(x.empreinte)).length;
  const aller = (pas) => { drive.position = Math.min(liste.length - 1, Math.max(0, drive.position + pas)); rendre(); };
  const personnes = p.auteurs.map((a) => [a.nom, a.prenom].filter(Boolean).join(", ")).join(" · ");
  const lignes = [["Titre", p.titre], ["Auteurs", personnes], ["Année", p.annee], ["DOI", p.doi]].filter(([, v]) => v);

  let decisions;
  if (f.deja) {
    decisions = h("div", { className: "decisions" },
      h("p", { className: "aide" }, "Déjà importé (reconnu à son contenu, même renommé)."),
      h("button", { className: "bouton", onclick: () => allerA(`#/sources/${f.deja.id}`) }, "Ouvrir la fiche"),
      h("button", { className: "bouton principal", onclick: suivantDossier }, "Suivant"));
  } else {
    decisions = h("div", { className: "decisions" },
      h("p", { className: "question" }, f.candidats.length
        ? (f.candidats.length > 1 ? "Est-ce l'une de ces sources ?" : "Est-ce cette source ?")
        : "Aucune source existante ne correspond."),
      f.candidats.map((c, i) => h("button", { className: "bouton candidat" + (i === 0 ? " principal" : ""), disabled: drive.enCours,
        onclick: () => deciderDossier(f, "joindre", c.id) },
        h("span", {}, `Oui : joindre à ${c.etiquette}`),
        h("span", { className: "detail" }, [c.titre, pluriel(c.nb_extraits, "extrait")].filter(Boolean).join(" · ")))),
      h("div", { className: "rangee" },
        h("button", { className: "bouton" + (f.candidats.length ? "" : " principal"), disabled: drive.enCours,
          onclick: () => deciderDossier(f, "creer") },
          `${f.candidats.length ? "Non, créer" : "Créer"} une source « ${LIBELLES_STATUT[f.statut]} »`),
        h("button", { className: "bouton discret", onclick: suivantDossier }, "Passer")));
  }

  return h("div", { className: "carte-biblio" },
    h("div", { className: "tete-biblio" },
      h("span", { className: "position" }, `Fichier ${drive.position + 1} sur ${liste.length}`),
      h("span", { className: "puce discrete" }, f.dossier),
      h("span", { className: "puce" }, LIBELLES_STATUT[f.statut]),
      h("span", { className: "compte" }, `${traites} traité${traites > 1 ? "s" : ""}`),
      h("button", { className: "icone", title: "Précédent", "aria-label": "Précédent", disabled: drive.position === 0,
        onclick: () => aller(-1) }, "‹"),
      h("button", { className: "icone", title: "Suivant", "aria-label": "Suivant", disabled: drive.position === liste.length - 1,
        onclick: () => aller(1) }, "›")),
    h("div", { className: "nom-fichier" }, f.relatif),
    f.debut ? [h("div", { className: "etiquette" }, "Début du texte"), h("p", { className: "debut-fichier" }, f.debut)]
      : h("p", { className: "aide petite" }, f.deja ? "" : "Aucun texte lisible (PDF scanné ?) : le fichier sera joint quand même."),
    lignes.length ? [h("div", { className: "etiquette" }, "Ce que l'outil en devine"),
      h("dl", { className: "champs-proposes" }, lignes.flatMap(([cle, v]) => [h("dt", {}, cle), h("dd", {}, v)]))] : null,
    decisions,
    h("p", { className: "aide petite" }, "Titre et auteurs se complètent ensuite dans la fiche de la source."));
}

function resumeDossiers() {
  const { fichiers, ignores } = drive.apercu;
  const passes = fichiers.filter((f) => !f.deja && !drive.faits.has(f.empreinte)).length;
  return h("div", { className: "carte-biblio" },
    h("p", {}, h("strong", {}, fichiers.length ? "Fichiers traités. " : "Aucun PDF dans ces dossiers. "),
      passes ? `${pluriel(passes, "fichier")} passé${passes > 1 ? "s" : ""} : relance l'analyse pour y revenir. ` : "",
      ignores.length ? `Laissés de côté : ${ignores.join(", ")}.` : ""),
    fichiers.length ? h("ul", { className: "resume-biblio" }, fichiers.map((f) => {
      const fait = drive.faits.get(f.empreinte);
      const id = fait?.source_id || f.deja?.id;
      const statut = fait ? (fait.action === "creer" ? "créée" : "joint") : f.deja ? "déjà là" : "passé";
      return h("li", {}, h("span", { className: "puce" + (id ? "" : " discrete") }, statut),
        id ? h("a", { href: `#/sources/${id}` }, f.nom) : h("span", {}, f.nom));
    })) : null);
}
