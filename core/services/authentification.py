"""
Logique de connexion et de mot de passe partagée par les pages thématiques.

Chaque application (visite client, rétablissement, …) a ses propres pages —
connexion, mot de passe oublié, réinitialisation, changement obligatoire,
auto-activation — dans son propre thème visuel. Mais une **seule** mécanique
de sécurité sous le capot : verrouillage anti brute-force, jetons de
réinitialisation, renouvellement de session, respect du `?next=`
inter-applications. Ce module est le point unique où cette mécanique est
implémentée ; les vues de chaque application n'en sont que des habillages
(gabarit + destinations par défaut).
"""
from __future__ import annotations

import logging
import secrets
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core import security, sso
from core.forms import ConnexionForm, DefinirMotDePasseForm, MotDePasseOublieForm, NouvelUtilisateurForm
from core.services.mailer import envoie_identifiants_activation, envoie_lien_reinitialisation

logger = logging.getLogger("dran.security")
Agent = get_user_model()

ESPACE_ACTIVATION = "activation-compte"


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------
def destination_apres_connexion(request, agent, destination_par_defaut: str, change_password_url_name: str) -> str:
    """
    Détermine où renvoyer l'agent après une connexion réussie.

    Respecte `?next=` s'il pointe vers ce site ou une application sœur
    déclarée dans `DR_HOTES_SSO` (voir `core.sso`) ; sinon retombe sur
    `destination_par_defaut`, propre à la page de connexion utilisée. Dans les
    deux cas, si l'agent doit changer son mot de passe, cette destination est
    conservée en `next=` du formulaire de changement — de l'application dont
    il s'agit —, pour être reprise juste après.
    """
    suivant = request.POST.get("next") or request.GET.get("next") or ""
    if suivant and sso.url_autorisee(
        suivant,
        hote_courant=request.get_host(),
        entrees=settings.DR_HOTES_SSO,
        https_requis=request.is_secure(),
    ):
        cible = suivant
    else:
        cible = destination_par_defaut

    if agent.must_change_password:
        return f"{reverse(change_password_url_name)}?next={quote(cible)}"
    return cible


def traite_connexion(
    request,
    template_name: str,
    destination_par_defaut: str,
    change_password_url_name: str = "visite_client:change_password",
):
    """
    Vue de connexion générique, réutilisée par chaque page de connexion
    thématique. Elles ne diffèrent que par leur gabarit et leurs destinations
    par défaut — jamais par la logique de sécurité.
    """
    if request.user.is_authenticated and request.method == "GET":
        return redirect(destination_par_defaut)

    formulaire = ConnexionForm(request=request, data=request.POST or None)

    if request.method == "POST":
        matricule_saisi = (request.POST.get("matricule") or "").strip()

        if security.est_bloque(request, matricule_saisi):
            messages.error(
                request,
                "Trop de tentatives infructueuses. Réessayez dans "
                f"{settings.DR_LOGIN_LOCKOUT_SECONDS // 60} minutes.",
            )
            return render(request, template_name, {"form": formulaire}, status=429)

        if formulaire.is_valid():
            agent = formulaire.agent
            security.reinitialise(request, matricule_saisi)
            login(request, agent)
            # Nouvelle session : neutralise une éventuelle fixation de session.
            request.session.cycle_key()
            request.session["agent_matricule"] = agent.matricule
            logger.info("Connexion réussie : %s depuis %s", agent.matricule, security.adresse_client(request))
            if agent.must_change_password:
                messages.warning(request, "Premier accès : définissez un nouveau mot de passe.")
            return redirect(
                destination_apres_connexion(request, agent, destination_par_defaut, change_password_url_name)
            )

        security.enregistre_echec(request, matricule_saisi)
        logger.info(
            "Échec de connexion pour %r depuis %s", matricule_saisi, security.adresse_client(request)
        )
        messages.error(request, "Identifiants invalides.")

    return render(request, template_name, {"form": formulaire})


# ---------------------------------------------------------------------------
# Changement de mot de passe (obligatoire ou volontaire)
# ---------------------------------------------------------------------------
def traite_changement_mot_de_passe(request, template_name: str, destination_par_defaut: str):
    """Formulaire de changement — atteint après connexion, obligatoire ou non."""
    formulaire = DefinirMotDePasseForm(agent=request.user, data=request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        formulaire.save(request.user)
        update_session_auth_hash(request, request.user)  # garde la session active
        logger.info("Mot de passe modifié pour %s", request.user.matricule)
        messages.success(request, "Mot de passe modifié.")

        suivant = request.POST.get("next") or request.GET.get("next") or ""
        if suivant and sso.url_autorisee(
            suivant,
            hote_courant=request.get_host(),
            entrees=settings.DR_HOTES_SSO,
            https_requis=request.is_secure(),
        ):
            return redirect(suivant)
        return redirect(destination_par_defaut)
    return render(request, template_name, {"form": formulaire, "next": request.GET.get("next", "")})


# ---------------------------------------------------------------------------
# Mot de passe oublié (lien de réinitialisation par email)
# ---------------------------------------------------------------------------
def traite_mot_de_passe_oublie(request, template_name: str, reset_url_name: str, login_url_name: str):
    """
    Envoie un lien de réinitialisation signé si l'email correspond à un
    compte actif — réponse neutre dans tous les cas (pas d'énumération).
    """
    formulaire = MotDePasseOublieForm(data=request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        agent = formulaire.agent_correspondant()
        if agent and agent.email:
            uid = urlsafe_base64_encode(force_bytes(agent.pk))
            token = default_token_generator.make_token(agent)
            lien = request.build_absolute_uri(
                reverse(reset_url_name, kwargs={"uidb64": uid, "token": token})
            )
            try:
                envoie_lien_reinitialisation(agent.email, lien)
            except Exception:
                logger.exception("Envoi du mail de réinitialisation impossible")
        messages.info(request, "Si un compte correspond à cet email, un lien vient d'être envoyé.")
        return redirect(login_url_name)
    return render(request, template_name, {"form": formulaire})


def traite_reinitialisation_mot_de_passe(
    request, uidb64: str, token: str, template_name: str, forgot_url_name: str, login_url_name: str
):
    """Vérifie le jeton signé puis laisse l'agent choisir un nouveau mot de passe."""
    agent = None
    try:
        agent = Agent.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (Agent.DoesNotExist, ValueError, TypeError, OverflowError):
        agent = None

    if agent is None or not default_token_generator.check_token(agent, token):
        messages.error(request, "Lien invalide ou expiré. Refaites une demande.")
        return redirect(forgot_url_name)

    formulaire = DefinirMotDePasseForm(agent=agent, data=request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        formulaire.save(agent)
        logger.info("Mot de passe réinitialisé pour %s", agent.matricule)
        messages.success(request, "Mot de passe mis à jour. Vous pouvez vous connecter.")
        return redirect(login_url_name)

    return render(request, template_name, {"form": formulaire, "validlink": True})


# ---------------------------------------------------------------------------
# Auto-activation (« nouvel utilisateur »)
# ---------------------------------------------------------------------------
def traite_nouvel_utilisateur(request, template_name: str, login_url_name: str):
    """
    Auto-activation : un agent jamais encore connecté récupère un mot de
    passe temporaire par email, plutôt que de partager un mot de passe unique
    connu de tous à l'import.
    """
    formulaire = NouvelUtilisateurForm(data=request.POST or None)

    if request.method == "POST" and formulaire.is_valid():
        email = formulaire.cleaned_data["email"]

        if security.trop_de_tentatives(request, email, ESPACE_ACTIVATION, settings.DR_ACTIVATION_MAX_TENTATIVES):
            messages.error(request, "Trop de demandes pour cet email. Réessayez plus tard.")
            return render(request, template_name, {"form": formulaire}, status=429)

        security.enregistre_tentative(request, email, ESPACE_ACTIVATION, settings.DR_ACTIVATION_FENETRE_SECONDES)

        agent = formulaire.agent_a_activer()
        if agent:
            mot_de_passe = secrets.token_urlsafe(9)
            agent.set_password(mot_de_passe)
            agent.must_change_password = True
            agent.save(update_fields=["password", "must_change_password"])
            try:
                envoie_identifiants_activation(agent.email, agent.matricule, mot_de_passe)
                logger.info("Activation envoyée pour %s", agent.matricule)
            except Exception:
                logger.exception("Envoi des identifiants d'activation impossible")

        messages.info(
            request, "Si un compte non activé correspond à cet email, un mot de passe vient d'être envoyé."
        )
        return redirect(login_url_name)

    return render(request, template_name, {"form": formulaire})
