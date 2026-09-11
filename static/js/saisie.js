// --- Capture GPS ------------------------------------------------------------
// Objectif : la position la plus precise possible, mais par defaut on
// prend celle que le GPS a trouvee - on n attend jamais une precision
// ideale avant de rendre la saisie utilisable. Un seul releve juste apres
// l activation de la localisation est souvent approximatif (le tout
// premier point renvoye vient parfois du wifi/reseau avant que la puce GPS
// n ait eu le temps de s affiner) : on suit la position (watchPosition)
// pendant une fenetre assez longue pour laisser au GPS le temps de
// converger, et on retient a tout moment le meilleur releve recu (la plus
// petite valeur d accuracy). Mais des le tout premier releve, quelle que
// soit sa precision, il est ecrit dans le formulaire et le dossier devient
// enregistrable : la fenetre continue seulement a affiner ce releve en
// arriere-plan si un meilleur point arrive avant la fin. La precision
// reste une information technique enregistree en base pour un usage
// ulterieur : elle n est jamais affichee a l utilisateur (seules les
// coordonnees le sont), et n empeche jamais de valider/enregistrer le
// dossier. La capture doit TOUJOURS aboutir a un resultat exploitable : si
// le GPS echoue completement (permission refusee, position indisponible,
// appareil sans GPS, timeout sans le moindre releve), on retombe sur une
// position par defaut (centre d Abidjan) plutot que de bloquer la saisie -
// mieux vaut une position approximative a corriger que pas de position du
// tout et un depanneur incapable d enregistrer son dossier.
const champLat = document.getElementById("id_latitude");
const champLon = document.getElementById("id_longitude");
const champPrecision = document.getElementById("id_precision_m");
const etatGps = document.getElementById("etat-gps");
const texteEtatGps = document.getElementById("texte-etat-gps");
const spinnerGps = document.getElementById("spinner-gps");
const boutonEnregistrer = document.getElementById("btn-enregistrer");
const boutonGps = document.getElementById("btn-gps");

// Fenetre d affinage interne assez longue pour laisser le GPS converger
// (la precision s ameliore souvent nettement apres les toutes premieres
// secondes), sans jamais bloquer l utilisateur : le premier releve rend
// deja la saisie utilisable, cette fenetre ne fait qu ameliorer le
// resultat en arriere-plan si possible.
const DUREE_AFFINAGE_MS = 25000;
// Repli si le GPS echoue completement : centre d Abidjan (meme valeur que
// le centre par defaut de la carte, cf. depannages/views.py:carte). Une
// precision tres degradee (99999 m) marque clairement en base qu il s agit
// d un repli et non d une vraie mesure GPS.
const POSITION_SECOURS = {latitude: 5.3600, longitude: -4.0083, accuracy: 99999};

let idSuiviGps = null;
let minuteurFinAffinage = null;
let meilleurReleve = null;

function afficherEtatGps(classe, texte) {
  etatGps.className = "message " + classe;
  texteEtatGps.textContent = texte;
}

function nettoyerSuivi() {
  if (idSuiviGps !== null) {
    navigator.geolocation.clearWatch(idSuiviGps);
    idSuiviGps = null;
  }
  if (minuteurFinAffinage !== null) {
    clearTimeout(minuteurFinAffinage);
    minuteurFinAffinage = null;
  }
  spinnerGps.hidden = true;
}

function enregistrerPosition(coords) {
  champLat.value = coords.latitude.toFixed(6);
  champLon.value = coords.longitude.toFixed(6);
  champPrecision.value = Math.round(coords.accuracy);
  // Ni Enregistrer ni Recapturer ne restent bloques par la recherche GPS :
  // des qu une position existe, le dossier peut etre enregistre, et une
  // nouvelle recherche peut etre relancee a tout moment.
  boutonEnregistrer.disabled = false;
  boutonGps.disabled = false;
  spinnerGps.hidden = true;
  // Uniquement les coordonnees dans le message : jamais la precision.
  afficherEtatGps("success", "Position captée : " + champLat.value + ", " + champLon.value);
}

function repliGps() {
  // Dernier recours : toujours donner un resultat plutot que de laisser la
  // saisie bloquee sans position exploitable.
  nettoyerSuivi();
  if (!champLat.value) {
    enregistrerPosition(POSITION_SECOURS);
  }
}

function capturerPosition() {
  if (!navigator.geolocation) {
    repliGps();
    return;
  }
  nettoyerSuivi();
  meilleurReleve = null;
  boutonGps.disabled = true;
  spinnerGps.hidden = false;
  afficherEtatGps("info", "Recherche de la position GPS en cours...");

  idSuiviGps = navigator.geolocation.watchPosition(
    (position) => {
      if (!meilleurReleve || position.coords.accuracy < meilleurReleve.coords.accuracy) {
        meilleurReleve = position;
        enregistrerPosition(position.coords);
      }
    },
    (erreur) => {
      // Une erreur ponctuelle (position momentanement indisponible,
      // sous-timeout interne au navigateur...) ne doit pas faire
      // abandonner la recherche : le GPS peut tres bien se reprendre et
      // livrer un releve, meme imprecis, juste apres. On ne bascule sur la
      // position de secours qu en dernier recours, si vraiment aucun
      // releve n a pu etre obtenu d ici la fin de la fenetre (cf. le
      // setTimeout ci-dessous) - sauf si la permission est carrement
      // refusee (code 1), auquel cas le GPS ne pourra plus jamais aboutir
      // et il est inutile d attendre la fin de la fenetre.
      if (erreur.code === 1) {
        repliGps();
      }
    },
    {enableHighAccuracy: true, maximumAge: 0, timeout: 30000}
  );
  minuteurFinAffinage = setTimeout(repliGps, DUREE_AFFINAGE_MS);
}
boutonGps.addEventListener("click", capturerPosition);
if (!champLat.value) capturerPosition();

// --- Photos : prise directe ou fichier joint, plusieurs images --------------
// Referencee depuis les onclick="declencher(...)" des boutons Prendre/Joindre :
// doit rester une fonction globale (pas dans une IIFE).
function declencher(champ, origine) {
  const input = document.getElementById("id_" + champ);
  // `capture` demande l'appareil photo ; sans l'attribut, le téléphone
  // propose la galerie et les fichiers.
  if (origine === "CAMERA") { input.setAttribute("capture", "environment"); }
  else { input.removeAttribute("capture"); }
  const origineChamp = document.getElementById("origine-" + champ);
  if (origineChamp) origineChamp.value = origine;
  input.click();
}

["photos_ouvrage", "photo_fiche_avis"].forEach(champ => {
  document.getElementById("id_" + champ).addEventListener("change", async (evenement) => {
    const input = evenement.target;
    const zone = document.getElementById("apercus-" + champ);
    zone.innerHTML = '<span class="aide">Compression des photos...</span>';

    // Compresse avant envoi : réseau terrain souvent faible.
    await compresserEtRemplacer(input);

    zone.innerHTML = "";
    [...input.files].forEach(fichier => {
      const image = document.createElement("img");
      image.src = URL.createObjectURL(fichier);
      image.className = "vignette";
      image.dataset.lightbox = image.src;
      image.dataset.lightboxLegende = fichier.name;
      zone.appendChild(image);
    });
    zone.closest(".zone-photo").classList.toggle("remplie", input.files.length > 0);
  });
});

// --- Segment Définitif / Provisoire ------------------------------------------
// Choisir "Définitif" clôture directement la part du dépanneur à la saisie
// (voir DepannageForm.save()) : les "Photos de l'ouvrage" déjà demandées
// servent aussi de preuve de clôture dans ce cas, pas de champ séparé.
function basculerProvisoire() {
  const choisi = document.querySelector("#segments-type input:checked");
  const provisoire = choisi && choisi.value === "PROVISOIRE";
  document.getElementById("segments-type").classList.toggle("provisoire", provisoire);
}
document.querySelectorAll("#segments-type input")
  .forEach(radio => radio.addEventListener("change", basculerProvisoire));
basculerProvisoire();

// --- Équipements : secteur (si DR coché) et nature du dossier (si Compteur
// coché) se déduisent des cases cochées, sans choix séparé. ------------------
const casesEquipement = document.querySelectorAll('input[name="equipements"]');
const blocSecteur = document.getElementById("bloc-secteur");
const champSecteur = document.getElementById("id_secteur");
const caseShunte = document.getElementById("case-shunte");
const caseCompteur = document.querySelector('input[name="equipements"][data-compteur="true"]');
const champCategorie = document.getElementById("champ-categorie");

// Vrai uniquement quand "Compteur" a été coché automatiquement par "Compteur
// shunté" (pas par un clic direct de l utilisateur sur "Compteur") : sert à
// masquer visuellement ce cochage silencieux (voir .masque-auto-coche).
let compteurAutoCoche = false;

function actualiserCategorie() {
  // "Compteur shunté" est toujours visible dans la liste, sans avoir à
  // cocher "Compteur" au préalable : le cocher coche donc automatiquement
  // l'équipement "Compteur" en arrière-plan (il n'existe qu'un seul
  // équipement "Compteur" en base ; "shunté" n'en est qu'une variante de
  // categorie_provisoire, pas un équipement distinct) - sans que l utilisateur
  // voie cette case se cocher toute seule.
  if (caseShunte.checked && caseCompteur && !caseCompteur.checked) {
    caseCompteur.checked = true;
    compteurAutoCoche = true;
    actualiserStructures();
    return; // actualiserStructures() rappelle actualiserCategorie() ensuite.
  }
  if (!caseShunte.checked && compteurAutoCoche) {
    // "Compteur shunté" est décoché : on retire discrètement le cochage
    // automatique qu il avait déclenché.
    caseCompteur.checked = false;
    compteurAutoCoche = false;
    actualiserStructures();
    return;
  }

  const compteurCoche = [...casesEquipement].some(c => c.checked && c.dataset.compteur === "true");
  if (!compteurCoche) caseShunte.checked = false;

  const categorie = !compteurCoche
    ? "AUTRE_EQUIPEMENT"
    : caseShunte.checked ? "COMPTEUR_SHUNTE" : "SANS_ELECTRICITE";
  champCategorie.value = categorie;

  const labelCompteur = caseCompteur ? caseCompteur.closest(".case") : null;
  if (labelCompteur) labelCompteur.classList.toggle("masque-auto-coche", compteurAutoCoche);
}
caseShunte.addEventListener("change", actualiserCategorie);

function actualiserStructures() {
  const cochees = [...casesEquipement].filter(c => c.checked);
  const structures = [...new Set(cochees.map(c => c.dataset.structure))];
  const concerneDR = cochees.some(c => c.dataset.typeStructure === "DR");

  blocSecteur.style.display = concerneDR ? "block" : "none";
  champSecteur.required = concerneDR;
  if (!concerneDR) champSecteur.value = "";

  document.getElementById("info-multi").style.display =
    structures.length > 1 ? "flex" : "none";
  // Le badge recapitulant les structures concernees (ex. "DRAN + DCRD") a
  // ete retire du gabarit ; le message #info-multi ci-dessus porte deja
  // cette information quand plusieurs structures sont concernees. On garde
  // ce garde-fou pour ne pas casser le reste du script si l element revient.
  const badgeStructures = document.getElementById("badge-structures");
  if (badgeStructures) {
    badgeStructures.textContent = structures.length ? structures.join(" + ") : "";
  }

  actualiserCategorie();
}
casesEquipement.forEach(c => c.addEventListener("change", actualiserStructures));
actualiserStructures();

// Évite le double envoi sur réseau lent.
document.getElementById("form-saisie").addEventListener("submit", () => {
  const bouton = document.getElementById("btn-enregistrer");
  bouton.disabled = true;
  bouton.textContent = "Enregistrement...";
});
