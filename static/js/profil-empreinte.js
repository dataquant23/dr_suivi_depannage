const versTampon = (valeur) => {
  const base64 = valeur.replace(/-/g, "+").replace(/_/g, "/");
  const brut = atob(base64.padEnd(base64.length + (4 - base64.length % 4) % 4, "="));
  return Uint8Array.from(brut, c => c.charCodeAt(0));
};
const versBase64Url = (tampon) =>
  btoa(String.fromCharCode(...new Uint8Array(tampon)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");

const afficher = (texte, type) => {
  document.getElementById("zone-message").innerHTML =
    '<div class="message ' + type + '">' + texte + "</div>";
};

const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
const boutonActiver = document.getElementById("btn-activer");

if (!window.PublicKeyCredential) {
  document.getElementById("bloc-activation").style.display = "none";
  document.getElementById("bloc-indisponible").style.display = "block";
} else {
  PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable().then(dispo => {
    if (!dispo) {
      document.getElementById("bloc-activation").style.display = "none";
      document.getElementById("bloc-indisponible").style.display = "block";
    }
  });
}

boutonActiver.addEventListener("click", async () => {
  try {
    const reponseDefi = await fetch(boutonActiver.dataset.urlDebut, {
      method: "POST", headers: {"X-CSRFToken": csrf},
    });
    const options = await reponseDefi.json();
    if (!reponseDefi.ok) { afficher(options.erreur, "error"); return; }

    options.challenge = versTampon(options.challenge);
    options.user.id = versTampon(options.user.id);
    (options.excludeCredentials || []).forEach(c => { c.id = versTampon(c.id); });

    // Demande l'empreinte : la clé privée est créée et gardée par le téléphone.
    const credential = await navigator.credentials.create({publicKey: options});

    const reponse = await fetch(boutonActiver.dataset.urlFin, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
      body: JSON.stringify({
        appareil: navigator.userAgentData?.platform || navigator.platform || "Téléphone",
        credential: {
          id: credential.id,
          rawId: versBase64Url(credential.rawId),
          type: credential.type,
          response: {
            clientDataJSON: versBase64Url(credential.response.clientDataJSON),
            attestationObject: versBase64Url(credential.response.attestationObject),
          },
        },
      }),
    });
    const resultat = await reponse.json();
    if (resultat.ok) {
      afficher(resultat.message + " Rechargement...", "success");
      setTimeout(() => window.location.reload(), 1200);
    } else {
      afficher(resultat.erreur, "error");
    }
  } catch (erreur) {
    afficher("Activation annulée.", "warning");
  }
});
