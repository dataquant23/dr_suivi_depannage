// --- Utilitaires d'encodage WebAuthn (base64url <-> ArrayBuffer) ---
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

const boutonEmpreinte = document.getElementById("btn-empreinte");

// L'option empreinte n'apparaît que si l'appareil dispose d'un capteur.
let bioDisponible = false;

if (window.PublicKeyCredential &&
    PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable) {
  PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable().then(dispo => {
    if (dispo) {
      bioDisponible = true;
      document.body.classList.add("auth-bio-disponible");
      document.getElementById("bloc-empreinte").style.display = "block";
      const memorise = localStorage.getItem("dernier_identifiant");
      if (memorise) document.getElementById("matricule-bio").value = memorise;
    }
  });
}

boutonEmpreinte?.addEventListener("click", async () => {
  const champBio = document.getElementById("matricule-bio");
  const champMotPasse = document.getElementById("id_matricule");
  const identifiant = (champBio.value || champMotPasse.value || "").trim();
  if (!bioDisponible) {
    afficher("Connexion par empreinte indisponible sur cet appareil. Utilisez votre identifiant.", "warning");
    document.getElementById("form-mot-passe").classList.add("ouvert");
    champMotPasse.focus();
    return;
  }
  if (!identifiant) {
    afficher("Utilisez d'abord votre identifiant, puis activez l'empreinte dans le profil.", "warning");
    document.getElementById("form-mot-passe").classList.add("ouvert");
    champMotPasse.focus();
    return;
  }

  try {
    const reponseDefi = await fetch(boutonEmpreinte.dataset.urlDebut, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRFToken": obtenirCsrf()},
      body: JSON.stringify({matricule: identifiant}),
    });
    const options = await reponseDefi.json();
    if (!reponseDefi.ok) { afficher(options.erreur, "error"); return; }

    options.challenge = versTampon(options.challenge);
    (options.allowCredentials || []).forEach(c => { c.id = versTampon(c.id); });

    // Déclenche la demande d'empreinte / Face ID par le système.
    const assertion = await navigator.credentials.get({publicKey: options});

    const reponse = await fetch(boutonEmpreinte.dataset.urlFin, {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-CSRFToken": obtenirCsrf()},
      body: JSON.stringify({
        credential: {
          id: assertion.id,
          rawId: versBase64Url(assertion.rawId),
          type: assertion.type,
          response: {
            clientDataJSON: versBase64Url(assertion.response.clientDataJSON),
            authenticatorData: versBase64Url(assertion.response.authenticatorData),
            signature: versBase64Url(assertion.response.signature),
            userHandle: assertion.response.userHandle
              ? versBase64Url(assertion.response.userHandle) : null,
          },
        },
      }),
    });
    const resultat = await reponse.json();
    if (resultat.ok) {
      localStorage.setItem("dernier_identifiant", identifiant);
      window.location.href = resultat.redirection;
    } else {
      afficher(resultat.erreur + " Utilisez votre mot de passe.", "error");
    }
  } catch (erreur) {
    afficher("Connexion par empreinte annulée. Utilisez votre mot de passe.", "warning");
  }
});

const boutonVoirMotPasse = document.getElementById("btn-voir-mot-passe");
boutonVoirMotPasse?.addEventListener("click", () => {
  const champ = document.getElementById("id_password");
  const visible = champ.type === "text";
  champ.type = visible ? "password" : "text";
  boutonVoirMotPasse.querySelector(".ico").classList.toggle("i-eye", visible);
  boutonVoirMotPasse.querySelector(".ico").classList.toggle("i-eye-off", !visible);
  boutonVoirMotPasse.setAttribute("aria-pressed", String(!visible));
  boutonVoirMotPasse.setAttribute("aria-label", visible ? "Afficher le mot de passe" : "Masquer le mot de passe");
});

function obtenirCsrf() {
  return document.querySelector("[name=csrfmiddlewaretoken]").value;
}
