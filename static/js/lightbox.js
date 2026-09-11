/**
 * Visionneuse plein ecran pour les pieces jointes : tout element portant
 * data-lightbox="<url image>" (et optionnellement data-lightbox-legende)
 * ouvre l image en grand au clic, avec fermeture par croix, touche Echap ou
 * clic en dehors de l image.
 */
(function () {
  let overlay = null;

  function construireOverlay() {
    overlay = document.createElement("div");
    overlay.className = "lightbox-overlay";
    overlay.innerHTML =
      '<button type="button" class="lightbox-fermer" aria-label="Fermer">' +
      '<span class="btn-symbol i-fermer" aria-hidden="true"></span></button>' +
      '<img class="lightbox-image" alt="">' +
      '<div class="lightbox-legende"></div>';
    document.body.appendChild(overlay);

    overlay.addEventListener("click", (evenement) => {
      if (evenement.target === overlay) fermer();
    });
    overlay.querySelector(".lightbox-fermer").addEventListener("click", fermer);
  }

  function ouvrir(url, legende) {
    if (!overlay) construireOverlay();
    overlay.querySelector(".lightbox-image").src = url;
    overlay.querySelector(".lightbox-legende").textContent = legende || "";
    overlay.classList.add("visible");
    document.body.style.overflow = "hidden";
  }

  function fermer() {
    if (!overlay) return;
    overlay.classList.remove("visible");
    document.body.style.overflow = "";
  }

  document.addEventListener("click", (evenement) => {
    const declencheur = evenement.target.closest("[data-lightbox]");
    if (!declencheur) return;
    evenement.preventDefault();
    ouvrir(declencheur.dataset.lightbox, declencheur.dataset.lightboxLegende);
  });

  document.addEventListener("keydown", (evenement) => {
    if (evenement.key === "Escape") fermer();
  });
})();
