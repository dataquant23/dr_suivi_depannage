"""Authentification : mot de passe (socle partagé) + empreinte via WebAuthn.

Connexion, changement et réinitialisation délèguent à
`core.services.authentification` ; ces vues ne font que fournir gabarit et
destinations. WebAuthn ne stocke que la clé publique, aucune donnée
biométrique.
"""

import base64
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from core.decorators import org_role_requise
from core.services.acces import traite_gestion_acces
from core.services.authentification import (
    traite_changement_mot_de_passe,
    traite_connexion,
    traite_mot_de_passe_oublie,
    traite_reinitialisation_mot_de_passe,
)
from depannages.profils import PROFILS

from .models import WebAuthnCredential

Agent = get_user_model()

CLE_DEFI_ENROLEMENT = "webauthn_defi_enrolement"
CLE_DEFI_CONNEXION = "webauthn_defi_connexion"
CLE_UTILISATEUR_CONNEXION = "webauthn_utilisateur_connexion"


def _b64(donnees: bytes) -> str:
    return base64.b64encode(donnees).decode()


def _debase64(valeur: str) -> bytes:
    return base64.b64decode(valeur)


# --- Connexion classique / mot de passe --------------------------------------


def connexion(request):
    return traite_connexion(
        request,
        "comptes/connexion.html",
        reverse("depannages:tableau_bord"),
        change_password_url_name="comptes:changer_mot_de_passe",
    )


def deconnexion(request):
    matricule = getattr(request.user, "matricule", "anonyme")
    logout(request)
    messages.info(request, "Vous êtes déconnecté.")
    return redirect("comptes:connexion")


@login_required
def changer_mot_de_passe(request):
    return traite_changement_mot_de_passe(
        request, "comptes/changer_mot_de_passe.html", reverse("depannages:tableau_bord")
    )


def mot_de_passe_oublie(request):
    return traite_mot_de_passe_oublie(
        request, "comptes/mot_de_passe_oublie.html", "comptes:mot_de_passe_reinitialiser", "comptes:connexion"
    )


def mot_de_passe_reinitialiser(request, uidb64: str, token: str):
    return traite_reinitialisation_mot_de_passe(
        request, uidb64, token, "comptes/mot_de_passe_reinitialiser.html", "comptes:mot_de_passe_oublie",
        "comptes:connexion",
    )


@login_required
def profil(request):
    return render(
        request,
        "comptes/profil.html",
        {"rubrique": "profil", "cles": request.user.cles_webauthn.all()},
    )


# --- Gestion des accès (rôle dépannage) --------------------------------------


@login_required
@org_role_requise("Direction régionale", "Responsable commercial", login_url="comptes:connexion")
def gestion_acces(request):
    return traite_gestion_acces(request, "depannages", PROFILS, "comptes/gestion_acces.html")


# --- WebAuthn : enrolement de l'empreinte -----------------------------------


@login_required
@require_POST
def webauthn_enrolement_debut(request):
    """Génère le défi ; le navigateur demandera l'empreinte à l'utilisateur."""
    deja_enrolees = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
        for c in request.user.cles_webauthn.all()
    ]
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(request.user.pk).encode(),
        user_name=request.user.matricule,
        user_display_name=str(request.user),
        exclude_credentials=deja_enrolees,
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Capteur intégré au téléphone, pas de clé USB.
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    request.session[CLE_DEFI_ENROLEMENT] = _b64(options.challenge)
    return JsonResponse(json.loads(options_to_json(options)))


@login_required
@require_POST
def webauthn_enrolement_fin(request):
    defi = request.session.pop(CLE_DEFI_ENROLEMENT, None)
    if not defi:
        return JsonResponse({"erreur": "Session d'enrôlement expirée."}, status=400)

    corps = json.loads(request.body)
    try:
        verification = verify_registration_response(
            credential=corps["credential"],
            expected_challenge=_debase64(defi),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            require_user_verification=True,
        )
    except Exception as erreur:
        return JsonResponse({"erreur": f"Enrôlement refusé : {erreur}"}, status=400)

    WebAuthnCredential.objects.create(
        utilisateur=request.user,
        credential_id=base64.urlsafe_b64encode(verification.credential_id)
        .decode()
        .rstrip("="),
        public_key=_b64(verification.credential_public_key),
        sign_count=verification.sign_count,
        libelle_appareil=corps.get("appareil", "")[:150] or "Téléphone",
    )
    return JsonResponse({"ok": True, "message": "Empreinte activée sur cet appareil."})


@login_required
@require_POST
def webauthn_supprimer(request, pk):
    cle = get_object_or_404(WebAuthnCredential, pk=pk, utilisateur=request.user)
    cle.delete()
    messages.success(request, "Appareil retiré. La connexion par mot de passe reste active.")
    return redirect("comptes:profil")


# --- WebAuthn : connexion par empreinte -------------------------------------


@require_POST
def webauthn_connexion_debut(request):
    matricule = json.loads(request.body or "{}").get("matricule", "").strip()
    if not matricule:
        return JsonResponse({"erreur": "Saisir le matricule."}, status=400)

    agent = Agent.objects.filter(matricule__iexact=matricule, is_active=True).first()
    if agent is None or not agent.cles_webauthn.exists():
        # Message neutre : on n'indique pas si le compte existe.
        return JsonResponse(
            {"erreur": "Aucune empreinte enrôlée pour ce matricule sur ce service."},
            status=404,
        )

    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in agent.cles_webauthn.all()
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    request.session[CLE_DEFI_CONNEXION] = _b64(options.challenge)
    request.session[CLE_UTILISATEUR_CONNEXION] = agent.pk
    return JsonResponse(json.loads(options_to_json(options)))


@require_POST
def webauthn_connexion_fin(request):
    defi = request.session.pop(CLE_DEFI_CONNEXION, None)
    agent_id = request.session.pop(CLE_UTILISATEUR_CONNEXION, None)
    if not defi or not agent_id:
        return JsonResponse({"erreur": "Session de connexion expirée."}, status=400)

    agent = Agent.objects.filter(pk=agent_id, is_active=True).first()
    if agent is None:
        return JsonResponse({"erreur": "Compte indisponible."}, status=400)

    corps = json.loads(request.body)
    credential = corps["credential"]
    cle = agent.cles_webauthn.filter(credential_id=credential["id"]).first()
    if cle is None:
        return JsonResponse({"erreur": "Appareil non reconnu."}, status=400)

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=_debase64(defi),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=_debase64(cle.public_key),
            credential_current_sign_count=cle.sign_count,
            require_user_verification=True,
        )
    except Exception as erreur:
        return JsonResponse({"erreur": f"Connexion refusée : {erreur}"}, status=400)

    cle.sign_count = verification.new_sign_count
    cle.derniere_utilisation = timezone.now()
    cle.save(update_fields=["sign_count", "derniere_utilisation"])

    login(request, agent, backend="core.backends.MatriculeBackend")
    return JsonResponse({"ok": True, "redirection": "/"})
