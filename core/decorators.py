"""Décorateurs d'autorisation communs aux deux applications."""
from __future__ import annotations

import logging
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger("dran.security")


# Caractères ré-encodés dans les réponses JSON : la charge reste identique
# après `JSON.parse`, mais ne peut pas fermer une balise si le contenu est un
# jour inséré dans du HTML (défense en profondeur contre le XSS).
ECHAPPEMENTS_JSON = {
    b"<": b"\\u003c",
    b">": b"\\u003e",
    b"&": b"\\u0026",
    b"\xe2\x80\xa8": b"\\u2028",
    b"\xe2\x80\xa9": b"\\u2029",
}


def json_no_cache(payload: dict, status: int = 200) -> JsonResponse:
    """Réponse JSON jamais mise en cache (données nominatives) et sûre en HTML."""
    response = JsonResponse(payload, status=status)
    contenu = response.content
    for brut, echappe in ECHAPPEMENTS_JSON.items():
        contenu = contenu.replace(brut, echappe)
    response.content = contenu
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _est_appel_api(request) -> bool:
    return (
        request.path.rstrip("/").endswith("/api")
        or "/api/" in request.path
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("Accept", "").startswith("application/json")
    )


def connexion_requise(view=None, *, login_url: str = "visite_client:login"):
    """
    Équivalent de `login_required`, compatible avec l'authentification unique
    ET avec plusieurs pages de connexion thématiques (une par application).

    `django.contrib.auth.decorators.login_required` construit un `?next=`
    relatif : renvoyé vers le portail central d'un autre sous-domaine, ce
    chemin désignerait une page de *ce* portail. On passe donc par
    `redirect_login`, qui produit une URL de retour absolue.

    Utilisable nu (`@connexion_requise`, page de connexion par défaut) ou
    paramétré (`@connexion_requise(login_url="recouvrement:login")`).
    """

    def _decorateur(v):
        @wraps(v)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if _est_appel_api(request):
                    return json_no_cache({"ok": False, "error": "Authentification requise."}, 401)
                return redirect_login(request, login_url=login_url)
            return v(request, *args, **kwargs)

        return _wrapped

    if view is not None:
        return _decorateur(view)
    return _decorateur


def permission_requise(
    permission: str,
    redirection: str = "core:accueil",
    message: str | None = None,
    login_url: str = "visite_client:login",
):
    """
    Exige une permission applicative (cf. `core.profils`).

    C'est le point d'entrée unique du contrôle d'accès par profil : une
    application entière peut être fermée à un profil en retirant une seule
    permission de la matrice, sans toucher aux vues. `login_url` détermine
    vers quelle page de connexion thématique renvoyer un visiteur anonyme.
    """

    def _decorateur(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if _est_appel_api(request):
                    return json_no_cache({"ok": False, "error": "Authentification requise."}, 401)
                return redirect_login(request, login_url=login_url)

            if not user.has_perm(permission):
                logger.warning(
                    "Accès refusé : %s ne possède pas %s (profil=%r) sur %s",
                    user.matricule,
                    permission,
                    user.profil,
                    request.path,
                )
                if _est_appel_api(request):
                    return json_no_cache({"ok": False, "error": "Accès refusé."}, 403)
                messages.error(request, message or "Accès refusé : votre profil ne permet pas cette action.")
                return redirect(redirection)
            return view(request, *args, **kwargs)

        return _wrapped

    return _decorateur


def droit_requis(
    code_application: str,
    catalogue_profils: dict,
    droit: str,
    *,
    redirection: str = "core:accueil",
    message: str | None = None,
    login_url: str = "visite_client:login",
):
    """
    Exige un droit du catalogue de profils d'une application (`core.AccesApplication`).

    Générique et réutilisé par chaque application : celle-ci ne fournit que
    son code, son catalogue local de profils (`<app>.profils.PROFILS`) et le
    nom du droit — voir `recouvrement/decorators.py`, `visite_client/decorators.py`,
    `coupure/decorators.py` pour les enveloppes fines qui pré-appliquent
    `code_application`/`catalogue_profils` propres à chaque application.
    """

    def _decorateur(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            from core.services.acces import a_le_droit

            user = request.user
            if not user.is_authenticated:
                if _est_appel_api(request):
                    return json_no_cache({"ok": False, "error": "Authentification requise."}, 401)
                return redirect_login(request, login_url=login_url)

            if not a_le_droit(user, code_application, droit, catalogue_profils):
                logger.warning(
                    "Accès refusé : %s n'a pas le droit %r sur %s (application=%s)",
                    user.matricule,
                    droit,
                    request.path,
                    code_application,
                )
                if _est_appel_api(request):
                    return json_no_cache({"ok": False, "error": "Accès refusé."}, 403)
                messages.error(request, message or "Accès refusé : votre profil ne permet pas cette action.")
                return redirect(redirection)
            return view(request, *args, **kwargs)

        return _wrapped

    return _decorateur


def org_role_requise(
    *roles: str, redirection: str = "core:accueil", login_url: str = "visite_client:login"
):
    """
    Réserve un écran à un rôle organisationnel (`agent.profil`, ex. « Direction
    régionale », « Responsable commercial »).

    Sert à ouvrir l'accès aux écrans « Gestion des accès » de chaque
    application — le rôle organisationnel reste global (`core.profils`),
    mais ne donne plus directement de droits applicatifs : voir
    `core.services.acces`.
    """

    def _decorateur(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                if _est_appel_api(request):
                    return json_no_cache({"ok": False, "error": "Authentification requise."}, 401)
                return redirect_login(request, login_url=login_url)

            if user.profil not in roles:
                logger.warning(
                    "Accès admin refusé : %s (rôle=%r) sur %s", user.matricule, user.profil, request.path
                )
                if _est_appel_api(request):
                    return json_no_cache({"ok": False, "error": "Accès refusé."}, 403)
                messages.error(
                    request, "Accès refusé : réservé à la direction régionale et aux responsables commerciaux."
                )
                return redirect(redirection)
            return view(request, *args, **kwargs)

        return _wrapped

    return _decorateur


def gestion_utilisateurs_requise(view):
    """Réserve l'espace de gestion des utilisateurs à la direction régionale (DR, ADR)."""
    from core.profils import GERER_UTILISATEURS

    return permission_requise(
        GERER_UTILISATEURS,
        redirection="core:accueil",
        message="Accès refusé : la gestion des utilisateurs est réservée à la direction régionale.",
    )(view)


def secteur_requis(view):
    """Exige qu'un secteur ait été choisi et mémorisé en session."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not (request.session.get("secteur") or "").strip():
            if _est_appel_api(request):
                return json_no_cache({"ok": False, "error": "Secteur non sélectionné."}, 400)
            messages.warning(request, "Choisissez d'abord un secteur.")
            return redirect("recouvrement:choisir_secteur")
        return view(request, *args, **kwargs)

    return _wrapped


def secteur_visite_requis(view):
    """Variante « visite client » : renvoie vers le portail des agences."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not (request.session.get("secteur") or "").strip():
            if _est_appel_api(request):
                return json_no_cache({"ok": False, "error": "Secteur non sélectionné."}, 400)
            messages.warning(request, "Choisissez d'abord un secteur.")
            return redirect("visite_client:portail_secteurs")
        return view(request, *args, **kwargs)

    return _wrapped


def redirect_login(request, login_url: str = "visite_client:login"):
    """
    Renvoie un visiteur anonyme vers la page de connexion.

    Dans un projet satellite, `DR_URL_CONNEXION` pointe vers le portail central
    (`https://dran.dxteriz.com/connexion/`) : l'agent s'identifie une seule
    fois, puis revient à l'adresse complète d'où il venait — cette délégation
    prime toujours sur `login_url`, qui ne s'applique qu'aux pages de
    connexion locales à ce projet.
    """
    from urllib.parse import urlencode

    from django.conf import settings
    from django.urls import reverse

    centrale = getattr(settings, "DR_URL_CONNEXION", "")
    if centrale:
        retour = request.build_absolute_uri()
        return redirect(f"{centrale.rstrip('/')}/?{urlencode({'next': retour})}")

    cible = reverse(login_url) if "/" not in login_url else login_url
    return redirect(f"{cible}?{urlencode({'next': request.get_full_path()})}")
