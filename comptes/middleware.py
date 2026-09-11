"""Force le renouvellement d'un mot de passe provisoire (`must_change_password`).

Équivalent de `core.middleware.ForcePasswordChangeMiddleware`, adapté aux
routes `comptes:*` de ce projet.
"""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import resolve

# Vues joignables malgré l'obligation (sinon boucle de redirection).
VUES_AUTORISEES = {
    "comptes:changer_mot_de_passe",
    "comptes:deconnexion",
    "comptes:connexion",
    "comptes:mot_de_passe_oublie",
    "comptes:mot_de_passe_reinitialiser",
}


class ChangementMotDePasseObligatoireMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utilisateur = getattr(request, "user", None)
        if (
            utilisateur is not None
            and utilisateur.is_authenticated
            and getattr(utilisateur, "must_change_password", False)
            and not self._est_autorisee(request)
        ):
            messages.info(
                request,
                "Choisissez un nouveau mot de passe pour activer votre compte.",
            )
            return redirect("comptes:changer_mot_de_passe")
        return self.get_response(request)

    def _est_autorisee(self, request):
        chemin = request.path_info
        if chemin.startswith(("/static/", "/media/")):
            return True
        try:
            correspondance = resolve(chemin)
        except Exception:
            return False
        # Pas d'exemption pour /admin/ (sinon un admin sous provisoire garde
        # tous ses droits sans jamais changer).
        nom = (
            f"{correspondance.app_name}:{correspondance.url_name}"
            if correspondance.app_name
            else correspondance.url_name
        )
        return nom in VUES_AUTORISEES
