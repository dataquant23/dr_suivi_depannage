// Bascule mobile entre la liste des dossiers et les etats par secteur, pour
// eviter d avoir a defiler toute la liste pour atteindre l autre bloc.
const miseEnPageTravaux = document.getElementById("travaux-page-layout");
document.querySelectorAll('input[name="vue-travaux"]').forEach(radio => {
  radio.addEventListener("change", () => {
    miseEnPageTravaux.classList.toggle("vue-secteurs", radio.value === "secteurs" && radio.checked);
  });
});

// Le filtre par onglet (À traiter / Shuntés / Sans courant / Autres) est
// desormais servi cote serveur (parametre ?categorie=...), pour rester
// coherent avec la pagination : voir depannages/views.py:travaux_en_cours
// et le rendu en <a> dans travaux_en_cours.html.
