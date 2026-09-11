// Referencee depuis les onclick="declencher(...)" des boutons Prendre/Joindre :
// doit rester une fonction globale (pas dans une IIFE).
function declencher(champ, origine) {
  const input = document.getElementById("id_" + champ);
  if (origine === "CAMERA") { input.setAttribute("capture", "environment"); }
  else { input.removeAttribute("capture"); }
  input.click();
}

["bon_depannage", "photos_equipement"].forEach(champ => {
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

document.getElementById("form-cloture").addEventListener("submit", () => {
  const bouton = document.getElementById("btn-valider");
  bouton.disabled = true;
  bouton.textContent = "Enregistrement...";
});
