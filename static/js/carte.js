(function () {
  const support = document.getElementById("carte-leaflet");
  const stage = document.getElementById("carte-stage");

  if (!window.L) {
    support.innerHTML =
      '<div class="carte-erreur"><strong>Carte indisponible</strong>' +
      "<span>La bibliothèque cartographique n'a pas pu se charger. Vérifiez la connexion " +
      "internet et rechargez la page.</span></div>";
    return;
  }

  const carte = L.map("carte-leaflet", {zoomControl: false}).setView(
    [parseFloat(stage.dataset.centreLat), parseFloat(stage.dataset.centreLon)], 12
  );
  // Pas de controle de zoom Leaflet natif (ancre a un coin) : les 4 coins de
  // la carte sont deja occupes par nos propres panneaux (outils, legende,
  // liste des depannages) qui passent par-dessus au clic. Le zoom rejoint
  // plutot la boite a outils existante, en haut a gauche.
  document.getElementById("outil-zoom-plus").addEventListener("click", () => carte.zoomIn());
  document.getElementById("outil-zoom-moins").addEventListener("click", () => carte.zoomOut());

  // Sur mobile il n'y a pas de survol pour lire les title="..." des boutons
  // de la boite a outils : un tap affiche le meme libelle brievement.
  document.querySelectorAll(".outils-carte button[title]").forEach((bouton) => {
    bouton.addEventListener("touchstart", () => {
      bouton.classList.add("montre-etiquette");
      clearTimeout(bouton._minuteurEtiquette);
      bouton._minuteurEtiquette = setTimeout(() => bouton.classList.remove("montre-etiquette"), 1500);
    }, {passive: true});
  });

  // Filtres repliables (mobile uniquement, sans effet sur desktop ou le
  // panneau reste toujours ouvert en CSS) : le bouton n existe qu en dessous
  // du seuil ou .filtres-carte-repliables devient un vrai panneau.
  const boutonFiltres = document.getElementById("btn-filtres-carte");
  const panneauFiltres = document.getElementById("filtres-carte-repliables");
  boutonFiltres?.addEventListener("click", () => {
    const ouvert = panneauFiltres.classList.toggle("ouvert");
    boutonFiltres.setAttribute("aria-expanded", String(ouvert));
  });

  // Legende : fixe sur desktop, popover a la demande sur mobile (bouton
  // dedie dans la boite a outils, invisible sur desktop en CSS).
  const boutonLegende = document.getElementById("bouton-legende-carte");
  const legende = document.querySelector(".legende");
  boutonLegende?.addEventListener("click", (evenement) => {
    evenement.stopPropagation();
    const ouverte = legende.classList.toggle("ouverte");
    boutonLegende.classList.toggle("actif", ouverte);
  });
  // tile.openstreetmap.org interdit l'usage en production hors tests/perso
  // (politique d'usage OSM) : CARTO fournit les mêmes données OSM sans clé API.
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(carte);

  // Un canevas de dimensions nulles au moment de l'initialisation Leaflet
  // produit une carte grise ; on force un recalcul une fois le CSS appliqué.
  requestAnimationFrame(() => carte.invalidateSize());
  window.addEventListener("resize", () => carte.invalidateSize());

  function couleurZone(intensite, total) {
    if (!total) return "#e7ece8";
    if (intensite > 0.75) return "#b42318";
    if (intensite > 0.5) return "#dc4a1d";
    if (intensite > 0.25) return "#ed6a00";
    if (intensite > 0.1) return "#f4a261";
    return "#8fc7a2";
  }

  const resumeZone = document.getElementById("resume-zone-carte");
  document.getElementById("fermer-resume-zone")?.addEventListener("click", () => {
    resumeZone.classList.remove("visible");
  });

  // Un seul niveau affiche a la fois (choix explicite dans la barre) :
  // "Communes" donne la vue d'ensemble, "Quartiers" zoome sur le detail. Les
  // deux gardent le meme comportement au clic : resume de la zone touchee.
  function libelleNiveau(niveau) {
    return niveau === "quartier" ? "Quartier" : "Commune";
  }

  function styleZone(niveau) {
    return niveau === "quartier"
      ? {color: "#5b7290", weight: 1.4, opacity: 0.7}
      : {color: "#0d2b4e", weight: 1.8, opacity: 0.6};
  }

  function afficherResumeZone(niveau, p) {
    resumeZone.classList.add("visible");
    resumeZone.innerHTML =
      '<button type="button" class="fermer-resume-zone" aria-label="Fermer le résumé">' +
      '<span class="btn-symbol i-fermer" aria-hidden="true"></span></button>' +
      '<span class="etiquette">' + libelleNiveau(niveau) + '</span>' +
      "<strong>" + p.nom + "</strong>" +
      (niveau === "quartier"
        ? "<p>" + (p.commune || "Commune non renseignée") + "</p>"
        : "") +
      '<div class="mini-stats-zone">' +
      "<span><b>" + p.total + "</b> dossiers</span>" +
      "<span><b>" + p.shuntes + "</b> shuntés</span>" +
      "<span><b>" + p.sans_electricite + "</b> sans courant</span>" +
      "<span><b>" + p.hors_delai + "</b> en retard</span>" +
      "</div>";
  }

  const ZOOM_PAR_NIVEAU = {commune: 12, quartier: 14};
  const coucheParNiveau = {commune: null, quartier: null};

  function chargerZones(niveau) {
    if (coucheParNiveau[niveau]) return Promise.resolve(coucheParNiveau[niveau]);
    return fetch(stage.dataset.urlZones + "?niveau=" + niveau)
      .then((r) => r.json())
      .then((donnees) => {
        const couche = L.geoJSON(donnees, {
          style: (entite) => ({
            ...styleZone(niveau),
            fillColor: couleurZone(entite.properties.intensite, entite.properties.total),
            fillOpacity: entite.properties.total ? 0.45 : 0.12,
          }),
          onEachFeature: (entite, sousCouche) => {
            const p = entite.properties;
            sousCouche.on("click", (evenement) => {
              L.DomEvent.stopPropagation(evenement);
              afficherResumeZone(niveau, p);
            });
            const style = styleZone(niveau);
            sousCouche.on("mouseover", () => sousCouche.setStyle({weight: style.weight + 1, opacity: 1}));
            sousCouche.on("mouseout", () => sousCouche.setStyle(style));
          },
        });
        coucheParNiveau[niveau] = couche;
        return couche;
      })
      .catch(() => {
        resumeZone.classList.add("visible");
        resumeZone.innerHTML =
          '<span class="etiquette">' + libelleNiveau(niveau) + 's</span>' +
          "<strong>Découpage indisponible</strong>" +
          "<p>Les dépannages restent visibles sur la carte.</p>";
        // Message d erreur passif (rien a cliquer dedans) : se referme tout
        // seul plutot que de rester affiche indefiniment sur la carte.
        setTimeout(() => resumeZone.classList.remove("visible"), 5000);
        return null;
      });
  }

  let niveauZoneActuel = null;
  function afficherNiveauZone(niveau, recentrer = true) {
    resumeZone.classList.remove("visible");
    chargerZones(niveau).then((couche) => {
      if (niveauZoneActuel && coucheParNiveau[niveauZoneActuel]) {
        carte.removeLayer(coucheParNiveau[niveauZoneActuel]);
      }
      niveauZoneActuel = niveau;
      if (couche) couche.addTo(carte);
    });
    if (recentrer) {
      const zoomCible = ZOOM_PAR_NIVEAU[niveau];
      if (niveau === "quartier" ? carte.getZoom() < zoomCible : carte.getZoom() > zoomCible) {
        carte.setZoom(zoomCible);
      }
    }
  }

  const selecteurNiveauZone = document.getElementById("filtre-niveau-zone");
  afficherNiveauZone(selecteurNiveauZone.value, false);
  selecteurNiveauZone.addEventListener("change", () => afficherNiveauZone(selecteurNiveauZone.value));

  const groupes = L.markerClusterGroup ? L.markerClusterGroup({maxClusterRadius: 55}) : L.layerGroup();
  carte.addLayer(groupes);

  let pointReference = null;
  let marqueurReference = null;
  let cercleRayon = null;
  let rayonActif = "";
  let dernierPoints = [];

  const outilRayon = document.getElementById("outil-rayon");
  const outilEffacer = document.getElementById("outil-effacer");
  const popoverCoord = document.getElementById("popover-coord");
  const popoverRayon = document.getElementById("popover-rayon");
  const resumePerimetre = document.getElementById("resume-perimetre");

  const echapper = (valeur) =>
    String(valeur ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  function fermerPopovers(sauf) {
    [popoverCoord, popoverRayon].forEach((p) => {
      if (p !== sauf) p.hidden = true;
    });
  }
  document.addEventListener("click", (evenement) => {
    const dansOutils = evenement.target.closest(".outils-carte, .popover-carte");
    if (!dansOutils) fermerPopovers(null);
    if (evenement.target.closest(".fermer-resume-zone")) {
      resumeZone.classList.remove("visible");
    }
  });

  const iconePin = (point) => {
    const depasse = point.etat_delai === "DEPASSE";
    // La couleur suit toujours la catégorie (cohérence avec la légende) ;
    // le retard se signale par la pulsation, pas par un changement de teinte.
    const couleur = point.couleur;
    const symbole =
      point.categorie === "COMPTEUR_SHUNTE" ? "!" : point.categorie === "SANS_ELECTRICITE" ? "~" : "+";
    return L.divIcon({
      className: "",
      html:
        '<div class="marqueur-pin' + (depasse ? " depasse" : "") + '" style="--marqueur:' + couleur + '">' +
        '<div class="tete">' + symbole + "</div>" +
        '<div class="pointe"></div>' +
        "</div>",
      iconSize: [30, 40],
      iconAnchor: [15, 38],
      popupAnchor: [0, -36],
    });
  };

  // --- Point de référence : position, choix carte, coordonnées -----------

  function definirPoint(lat, lon, source, recentrer = true) {
    pointReference = {lat, lon, source};

    if (marqueurReference) carte.removeLayer(marqueurReference);
    marqueurReference = L.marker([lat, lon], {
      icon: L.divIcon({className: "", html: '<div class="marqueur-reference-carte"></div>', iconSize: [22, 22], iconAnchor: [11, 11]}),
      draggable: true,
      zIndexOffset: 1000,
    }).addTo(carte);
    marqueurReference.bindPopup(
      "<strong>Point de référence</strong><br>" + lat.toFixed(5) + ", " + lon.toFixed(5) +
      "<br><span style='color:#64748b'>Déplacez le marqueur pour ajuster.</span>"
    );
    marqueurReference.on("dragend", (evenement) => {
      const p = evenement.target.getLatLng();
      definirPoint(p.lat, p.lng, "CARTE", false);
    });

    document.getElementById("saisie-lat").value = lat.toFixed(6);
    document.getElementById("saisie-lon").value = lon.toFixed(6);
    outilRayon.disabled = false;
    outilEffacer.disabled = false;
    [document.getElementById("mode-gps"), document.getElementById("mode-coord")]
      .forEach((b) => b.classList.toggle("actif", b.dataset.source === source));

    if (recentrer && !rayonActif) carte.setView([lat, lon], 13);
    dessinerRayon();
    charger();
  }

  function retirerPoint() {
    pointReference = null;
    rayonActif = "";
    if (marqueurReference) { carte.removeLayer(marqueurReference); marqueurReference = null; }
    if (cercleRayon) { carte.removeLayer(cercleRayon); cercleRayon = null; }
    document.querySelectorAll(".puces-rayon button[data-rayon]").forEach((b) => b.classList.toggle("actif", b.dataset.rayon === ""));
    document.querySelectorAll("#mode-gps, #mode-coord").forEach((b) => b.classList.remove("actif"));
    outilRayon.disabled = true;
    outilEffacer.disabled = true;
    fermerPopovers(null);
    charger();
  }

  function dessinerRayon() {
    if (cercleRayon) { carte.removeLayer(cercleRayon); cercleRayon = null; }
    if (pointReference && rayonActif) {
      cercleRayon = L.circle([pointReference.lat, pointReference.lon], {
        radius: parseFloat(rayonActif) * 1000,
        color: "#0f6f3f", fillColor: "#0f6f3f", fillOpacity: 0.07, weight: 1.5,
      }).addTo(carte);
      carte.fitBounds(cercleRayon.getBounds(), {padding: [30, 30]});
    }
  }

  function localiser() {
    if (!navigator.geolocation) {
      afficherErreurLocalisation("La géolocalisation n'est pas prise en charge par ce navigateur.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => definirPoint(position.coords.latitude, position.coords.longitude, "GPS"),
      (erreur) => {
        // Sans ce retour, un clic sur "Ma position" refusé ou en échec ne
        // provoquait aucun changement visible : on ne savait pas si le
        // bouton avait réagi.
        const messages = {
          1: "Localisation refusée. Autorisez l'accès à la position dans les paramètres du navigateur.",
          2: "Position indisponible. Vérifiez que la localisation est activée sur l'appareil.",
          3: "La localisation a pris trop de temps. Réessayez.",
        };
        afficherErreurLocalisation(messages[erreur.code] || "Impossible d'obtenir votre position.");
      },
      {enableHighAccuracy: true, timeout: 12000}
    );
  }

  function afficherErreurLocalisation(texte) {
    resumeZone.classList.add("visible");
    resumeZone.innerHTML =
      '<button type="button" class="fermer-resume-zone" aria-label="Fermer le résumé">' +
      '<span class="btn-symbol i-fermer" aria-hidden="true"></span></button>' +
      '<span class="etiquette">Ma position</span>' +
      "<strong>Localisation impossible</strong>" +
      "<p>" + echapper(texte) + "</p>";
  }

  // --- Fiche détail d'un point (panneau de droite) ------------------------

  function afficherFiche(point) {
    fermerPopovers(null);
    document.getElementById("liste-points").hidden = true;
    const fiche = document.getElementById("fiche-point");
    fiche.hidden = false;
    // Sur mobile, on étend la feuille (et on l'affiche si elle était rangée)
    // pour que le détail choisi soit immédiatement visible.
    document.querySelector(".panneau-carte").classList.remove("masque");
    document.querySelector(".panneau-carte").classList.add("etendu");

    const retard = point.etat_delai === "DEPASSE"
      ? '<span class="badge rouge">Dépassé +' + point.retard + " h</span>"
      : point.etat_delai === "BIENTOT"
        ? '<span class="badge orange">Échéance proche</span>'
        : '<span class="badge vert">Dans les délais</span>';

    fiche.innerHTML =
      '<button type="button" class="retour" id="btn-retour-liste">' +
      '<span class="btn-symbol i-fleche-gauche" aria-hidden="true"></span> Retour à la liste</button>' +
      "<h3>" + echapper(point.numero_bt) + "</h3>" +
      '<div class="sous-structure">' + echapper((point.structures || []).join(" + ")) + "</div>" +
      '<span class="badge ' + (point.categorie === "COMPTEUR_SHUNTE" ? "orange" : point.categorie === "SANS_ELECTRICITE" ? "rouge" : "bleu") + '">' +
      echapper(point.categorie_libelle) + "</span> " + retard +
      '<div class="groupe-info">Informations</div>' +
      '<dl class="paire">' +
      "<dt>Secteur</dt><dd>" + echapper(point.secteur) + "</dd>" +
      // Pour "Autre équipement" la catégorie seule ne dit pas de quel
      // équipement il s'agit (contrairement à shunté/sans électricité, qui
      // pointent toujours vers le compteur) : on précise la liste ici.
      (point.categorie === "AUTRE_EQUIPEMENT" && (point.equipements || []).length
        ? "<dt>Équipement</dt><dd>" + echapper(point.equipements.join(", ")) + "</dd>"
        : "") +
      (point.distance_km !== null ? "<dt>Distance</dt><dd>" + point.distance_km + " km du point</dd>" : "") +
      "</dl>" +
      '<div class="actions-fiche">' +
      '<a href="' + echapper(point.url) + '" class="btn secondaire">Voir le dossier</a>' +
      (point.url_maps
        ? '<a href="' + echapper(point.url_maps) + '" target="_blank" rel="noopener" class="btn secondaire">' +
          '<span class="btn-symbol i-map" aria-hidden="true"></span> Itinéraire vers le site</a>'
        : "") +
      "</div>";

    document.getElementById("btn-retour-liste").addEventListener("click", masquerFiche);
  }

  function masquerFiche() {
    document.getElementById("fiche-point").hidden = true;
    document.getElementById("liste-points").hidden = false;
  }

  // --- Chargement des points ---------------------------------------------

  async function charger() {
    const parametres = new URLSearchParams({
      q: document.getElementById("filtre-bt").value.trim(),
      secteur: document.getElementById("filtre-secteur").value,
    });
    if (pointReference) {
      parametres.set("lat", pointReference.lat);
      parametres.set("lon", pointReference.lon);
      if (rayonActif) parametres.set("rayon", rayonActif);
    }

    let donnees;
    try {
      const reponse = await fetch(stage.dataset.urlDonnees + "?" + parametres);
      donnees = await reponse.json();
    } catch (erreur) {
      document.getElementById("liste-points").innerHTML = '<div class="vide">Impossible de charger les dépannages.</div>';
      return;
    }

    dernierPoints = donnees.points;
    groupes.clearLayers();
    document.getElementById("compte-total").textContent = donnees.total;

    const limites = [];
    const lignes = donnees.points.map((point) => {
      const marqueur = L.marker([point.lat, point.lon], {icon: iconePin(point)});
      marqueur.on("click", () => afficherFiche(point));
      groupes.addLayer(marqueur);
      limites.push([point.lat, point.lon]);

      const retard = point.etat_delai === "DEPASSE"
        ? '<span class="badge rouge">+' + point.retard + " h</span>"
        : point.etat_delai === "BIENTOT" ? '<span class="badge orange">Proche</span>' : "";

      return (
        '<div class="ligne-point" data-id="' + point.id + '">' +
        '<div class="ligne-point-entete">' +
        '<span class="puce" style="background:' + point.couleur + '"></span>' +
        "<strong>" + echapper(point.numero_bt) + "</strong>" + retard +
        "</div>" +
        '<div class="ligne-point-detail">' + echapper(point.secteur) +
        (point.distance_km !== null ? " &middot; " + point.distance_km + " km" : "") +
        "</div></div>"
      );
    });

    document.getElementById("liste-points").innerHTML =
      lignes.join("") || '<div class="vide">Aucun dépannage à afficher.</div>';
    document.querySelectorAll(".ligne-point").forEach((ligne) => {
      ligne.addEventListener("click", () => {
        const point = dernierPoints.find((p) => String(p.id) === ligne.dataset.id);
        if (point) afficherFiche(point);
      });
    });

    if (pointReference && rayonActif) {
      const origine = {GPS: "votre position", CARTE: "le point choisi", COORD: "les coordonnées saisies"}[pointReference.source];
      resumePerimetre.textContent = donnees.total + " dans un rayon de " + rayonActif + " km autour de " + origine + ".";
    } else if (pointReference) {
      resumePerimetre.textContent = "Point de référence placé. Choisissez un rayon dans les outils.";
    } else {
      resumePerimetre.textContent = "";
    }

    if (limites.length && !pointReference) carte.fitBounds(limites, {padding: [40, 40]});
  }

  // --- Branchements des contrôles -----------------------------------------

  document.getElementById("mode-gps").dataset.source = "GPS";
  document.getElementById("mode-coord").dataset.source = "COORD";

  document.getElementById("mode-gps").addEventListener("click", () => {
    fermerPopovers(null);
    localiser();
  });
  document.getElementById("mode-coord").addEventListener("click", (evenement) => {
    evenement.stopPropagation();
    const ouvert = !popoverCoord.hidden;
    fermerPopovers(null);
    popoverCoord.hidden = ouvert;
  });
  document.getElementById("outil-rayon").addEventListener("click", (evenement) => {
    evenement.stopPropagation();
    if (outilRayon.disabled) return;
    const ouvert = !popoverRayon.hidden;
    fermerPopovers(null);
    popoverRayon.hidden = ouvert;
  });
  document.getElementById("outil-effacer").addEventListener("click", retirerPoint);

  document.getElementById("btn-placer-coord").addEventListener("click", () => {
    const lat = parseFloat(document.getElementById("saisie-lat").value);
    const lon = parseFloat(document.getElementById("saisie-lon").value);
    if (Number.isNaN(lat) || Number.isNaN(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
    definirPoint(lat, lon, "COORD");
    popoverCoord.hidden = true;
  });

  function appliquerRayon(valeur, bouton) {
    document.querySelectorAll(".puces-rayon button[data-rayon]").forEach((b) => b.classList.remove("actif"));
    if (bouton) bouton.classList.add("actif");
    rayonActif = valeur;
    dessinerRayon();
    charger();
  }
  document.querySelectorAll(".puces-rayon button[data-rayon]").forEach((bouton) => {
    bouton.addEventListener("click", () => {
      document.getElementById("rayon-perso").value = "";
      appliquerRayon(bouton.dataset.rayon, bouton);
    });
  });
  document.getElementById("rayon-perso").addEventListener("change", (evenement) => {
    const valeur = parseFloat(evenement.target.value);
    if (Number.isNaN(valeur) || valeur <= 0) return;
    appliquerRayon(String(valeur), null);
  });

  document.getElementById("btn-plein-ecran").addEventListener("click", () => {
    const conteneur = document.getElementById("carte-stage");
    if (!document.fullscreenElement) conteneur.requestFullscreen?.();
    else document.exitFullscreen?.();
  });
  document.addEventListener("fullscreenchange", () => {
    const icone = document.querySelector("#btn-plein-ecran .btn-symbol");
    const plein = !!document.fullscreenElement;
    icone.classList.toggle("i-plein-ecran", !plein);
    icone.classList.toggle("i-reduire", plein);
    setTimeout(() => carte.invalidateSize(), 150);
  });

  document.getElementById("filtre-bt").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); charger(); }
  });
  document.getElementById("filtre-secteur").addEventListener("change", charger);

  // Sur mobile, le panneau est une feuille à 3 positions : normale (aperçu),
  // étendue (liste complète) et rangée (la carte occupe tout l'écran). La
  // poignée fait passer d'une position à l'autre.
  const panneauCarte = document.querySelector(".panneau-carte");
  const suivante = {normal: "etendu", etendu: "masque", masque: "normal"};
  document.getElementById("poignee-panneau").addEventListener("click", () => {
    const actuel = panneauCarte.classList.contains("masque")
      ? "masque"
      : panneauCarte.classList.contains("etendu")
        ? "etendu"
        : "normal";
    panneauCarte.classList.remove("etendu", "masque");
    const cible = suivante[actuel];
    if (cible !== "normal") panneauCarte.classList.add(cible);
  });

  charger();
})();
