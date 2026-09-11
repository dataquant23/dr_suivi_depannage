// Feuille "Plus" du menu mobile (Alertes/Rapports/Parametres), reservee aux
// responsables : evite de surcharger la barre du bas a 7 icones.
(function () {
  const bouton = document.getElementById("bouton-plus-mobile");
  const fond = document.getElementById("plus-mobile-fond");
  const feuille = document.getElementById("plus-mobile-feuille");
  if (!bouton || !fond || !feuille) return;

  function ouvrir() {
    fond.hidden = false;
    feuille.hidden = false;
    // Le hidden retire l element de l affichage : on laisse le navigateur
    // peindre cet etat avant d ajouter la classe qui declenche la
    // transition, sinon l apparition saute sans glisser.
    requestAnimationFrame(() => {
      fond.classList.add("ouvert");
      feuille.classList.add("ouvert");
    });
    bouton.setAttribute("aria-expanded", "true");
  }
  function fermer() {
    fond.classList.remove("ouvert");
    feuille.classList.remove("ouvert");
    bouton.setAttribute("aria-expanded", "false");
    // On attend la fin de la transition de sortie avant de retirer la
    // feuille du flux (hidden), pour qu elle se range visiblement au lieu
    // de disparaitre d un coup.
    setTimeout(() => {
      if (!feuille.classList.contains("ouvert")) {
        fond.hidden = true;
        feuille.hidden = true;
      }
    }, 200);
  }

  bouton.addEventListener("click", () => {
    feuille.hidden ? ouvrir() : fermer();
  });
  fond.addEventListener("click", fermer);
  // Se ranger des qu une option est choisie, plutot que d attendre le
  // chargement de la page suivante (visuellement plus net, et couvre le
  // cas d un lien vers la page deja affichee, qui ne recharge rien).
  feuille.addEventListener("click", (evenement) => {
    if (evenement.target.closest("a")) fermer();
  });
  document.addEventListener("keydown", (evenement) => {
    if (evenement.key === "Escape" && !feuille.hidden) fermer();
  });
})();
