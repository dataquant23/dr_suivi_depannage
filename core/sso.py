"""
Analyse des entrées d'authentification unique (`DR_HOTES_SSO`).

Contexte : `dran.dxteriz.com` héberge DRAN (visite client + rétablissement) à
la racine. `innovation.dxteriz.com` héberge **plusieurs applications
indépendantes** sous des préfixes de chemin (`/navig_poste`,
`/quartier_hors_tension`, …), déployées comme autant de projets Django
séparés derrière un reverse proxy. Seules certaines de ces applications
partagent la connexion avec DRAN — pas toutes.

Une entrée de `DR_HOTES_SSO` s'écrit :

    hôte                    -> confiance totale sur cet hôte (tous les chemins)
    hôte/préfixe            -> confiance limitée à ce préfixe uniquement

Exemple :

    DR_HOTES_SSO=dran.dxteriz.com,innovation.dxteriz.com/navig_poste

Ici, une redirection post-connexion vers `innovation.dxteriz.com/navig_poste/…`
est acceptée ; une redirection vers `innovation.dxteriz.com/quartier_hors_tension/…`
est refusée, car cette application n'a pas déclaré vouloir participer.

Ce module ne dépend d'aucun modèle Django : il est appelable depuis
`settings.py` sans risque d'import circulaire.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from django.utils.http import url_has_allowed_host_and_scheme


def parse_entree(entree: str) -> tuple[str, str]:
    """« innovation.dxteriz.com/navig_poste » -> (« innovation.dxteriz.com », « /navig_poste »)."""
    entree = (entree or "").strip().rstrip("/")
    if "/" in entree:
        hote, _, chemin = entree.partition("/")
        return hote, f"/{chemin}"
    return entree, ""


def parse_entrees(entrees) -> list[tuple[str, str]]:
    return [parse_entree(e) for e in (entrees or []) if e and e.strip()]


def hotes(entrees) -> list[str]:
    """Hôtes déclarés, dédupliqués, sans leur préfixe — pour CSRF_TRUSTED_ORIGINS et les contrôles."""
    vus: list[str] = []
    for hote, _ in parse_entrees(entrees):
        if hote not in vus:
            vus.append(hote)
    return vus


def url_autorisee(url: str, *, hote_courant: str, entrees, https_requis: bool) -> bool:
    """
    Une redirection post-connexion est autorisée si :

      * elle reste sur l'hôte courant, quel que soit le chemin (aucune
        application ne se restreint elle-même) ; ou
      * elle vise un hôte déclaré dans `entrees`, et que son chemin commence
        par un des préfixes autorisés pour cet hôte — ou que l'hôte est
        déclaré sans préfixe (confiance totale, rétrocompatible avec un
        déploiement un-hôte-par-application).

    Toute autre cible est refusée : c'est le garde-fou contre la redirection
    ouverte, et c'est aussi ce qui empêche une application non concernée par
    le SSO de recevoir un agent qu'elle ne sait pas authentifier.
    """
    if not url:
        return False

    entrees_analysees = parse_entrees(entrees)
    hotes_autorises = {hote_courant, *(h for h, _ in entrees_analysees)}
    if not url_has_allowed_host_and_scheme(url, allowed_hosts=hotes_autorises, require_https=https_requis):
        return False

    parties = urlsplit(url)
    cible = parties.netloc or hote_courant
    if cible == hote_courant:
        return True

    prefixes = [prefixe for hote, prefixe in entrees_analysees if hote == cible]
    if any(prefixe == "" for prefixe in prefixes):
        return True

    chemin = parties.path or "/"
    return any(chemin == prefixe or chemin.startswith(f"{prefixe}/") for prefixe in prefixes)
