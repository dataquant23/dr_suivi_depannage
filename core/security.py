"""Limitation du nombre de tentatives (connexion, activation de compte...)."""
from __future__ import annotations

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("dran.security")

ESPACE_CONNEXION = "login-attempts"


def adresse_client(request) -> str:
    """IP de l'appelant, en tenant compte d'un éventuel reverse proxy de confiance."""
    if getattr(settings, "USE_X_FORWARDED_HOST", False):
        transmis = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if transmis:
            return transmis.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "inconnue"


def _cle(request, identifiant: str, espace: str) -> str:
    empreinte = hashlib.sha256(
        f"{adresse_client(request)}|{(identifiant or '').lower()}".encode("utf-8")
    ).hexdigest()
    return f"{espace}:{empreinte}"


def compte_tentatives(request, identifiant: str, espace: str) -> int:
    return cache.get(_cle(request, identifiant, espace), 0)


def trop_de_tentatives(request, identifiant: str, espace: str, maximum: int) -> bool:
    return compte_tentatives(request, identifiant, espace) >= maximum


def enregistre_tentative(request, identifiant: str, espace: str, fenetre_secondes: int) -> int:
    cle = _cle(request, identifiant, espace)
    nombre = cache.get(cle, 0) + 1
    cache.set(cle, nombre, fenetre_secondes)
    return nombre


def reinitialise_tentatives(request, identifiant: str, espace: str) -> None:
    cache.delete(_cle(request, identifiant, espace))


# --------------------------------------------------------------------------
# Alias historiques : anti brute-force sur le formulaire de connexion.
# --------------------------------------------------------------------------
def tentatives(request, identifiant: str) -> int:
    return compte_tentatives(request, identifiant, ESPACE_CONNEXION)


def est_bloque(request, identifiant: str) -> bool:
    return trop_de_tentatives(request, identifiant, ESPACE_CONNEXION, settings.DR_LOGIN_MAX_ATTEMPTS)


def enregistre_echec(request, identifiant: str) -> int:
    nombre = enregistre_tentative(request, identifiant, ESPACE_CONNEXION, settings.DR_LOGIN_LOCKOUT_SECONDS)
    if nombre >= settings.DR_LOGIN_MAX_ATTEMPTS:
        logger.warning(
            "Blocage temporaire des connexions pour %s depuis %s (%s échecs)",
            identifiant,
            adresse_client(request),
            nombre,
        )
    return nombre


def reinitialise(request, identifiant: str) -> None:
    reinitialise_tentatives(request, identifiant, ESPACE_CONNEXION)
