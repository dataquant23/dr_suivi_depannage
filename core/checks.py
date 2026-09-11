"""
Contrôles de cohérence de l'authentification unique.

Une authentification unique mal configurée échoue de façon silencieuse : les
agents sont déconnectés d'une application à l'autre sans message d'erreur, ou
— plus grave — le cookie de session est exposé à des sous-domaines qui n'ont
rien à voir. Ces contrôles s'exécutent à chaque `manage.py check`, `runserver`
et déploiement.
"""
from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

from core import sso

IDENTIFIANT = "dran.sso"


@register(Tags.security)
def verifie_authentification_unique(app_configs, **kwargs):
    problemes = []
    entrees_brutes = getattr(settings, "DR_HOTES_SSO", [])

    if not entrees_brutes:
        return problemes

    hotes = sso.hotes(entrees_brutes)
    entrees = sso.parse_entrees(entrees_brutes)

    # Un hôte à la fois « bare » (confiance totale) et « préfixé » est
    # contradictoire : soit il héberge une seule application (pas besoin de
    # préfixe), soit plusieurs (le bare-host rend le préfixe inutile, puisque
    # la confiance totale l'englobe déjà).
    par_hote: dict[str, list[str]] = {}
    for hote, prefixe in entrees:
        par_hote.setdefault(hote, []).append(prefixe)
    ambigus = [hote for hote, prefixes in par_hote.items() if "" in prefixes and len(set(prefixes)) > 1]
    if ambigus:
        problemes.append(
            Warning(
                "Hôte(s) déclaré(s) à la fois en confiance totale et avec un préfixe "
                "restreint : " + ", ".join(ambigus) + ".",
                hint=(
                    "La confiance totale (« hôte » seul) englobe déjà tous les préfixes : "
                    "l'entrée préfixée est sans effet. Retirez l'une des deux déclarations."
                ),
                id=f"{IDENTIFIANT}.W005",
            )
        )

    if not settings.SESSION_COOKIE_DOMAIN:
        problemes.append(
            Warning(
                "Authentification unique déclarée sans domaine de cookie partagé.",
                hint=(
                    "Les applications de %s ne se reconnaîtront pas. Renseignez "
                    "DJANGO_COOKIE_DOMAIN avec le domaine parent, ex. « .dxteriz.com »."
                )
                % ", ".join(hotes),
                id=f"{IDENTIFIANT}.W001",
            )
        )
    else:
        domaine = settings.SESSION_COOKIE_DOMAIN.lstrip(".")
        hors_domaine = [hote for hote in hotes if not hote.endswith(domaine)]
        if hors_domaine:
            problemes.append(
                Error(
                    "Des hôtes déclarés en authentification unique ne sont pas sous "
                    f"« {settings.SESSION_COOKIE_DOMAIN} » : {', '.join(hors_domaine)}.",
                    hint=(
                        "Un cookie ne franchit pas la frontière d'un domaine. Ces "
                        "applications ont besoin d'un fournisseur d'identité (OIDC) "
                        "plutôt que d'un cookie partagé."
                    ),
                    id=f"{IDENTIFIANT}.E001",
                )
            )

    if not settings.DEBUG and not settings.SESSION_COOKIE_SECURE:
        problemes.append(
            Error(
                "Cookie de session partagé entre sous-domaines sans l'attribut Secure.",
                hint="Passez DJANGO_COOKIE_SECURE=1 : le cookie circulerait en clair.",
                id=f"{IDENTIFIANT}.E002",
            )
        )

    if not settings.DEBUG and str(settings.SECRET_KEY).startswith("django-insecure-"):
        problemes.append(
            Error(
                "Clé secrète générée automatiquement alors que l'authentification unique est active.",
                hint=(
                    "Toutes les applications doivent partager la MÊME DJANGO_SECRET_KEY, "
                    "sinon les sessions sont rejetées d'une application à l'autre."
                ),
                id=f"{IDENTIFIANT}.E003",
            )
        )

    if settings.SESSION_ENGINE != "django.contrib.sessions.backends.db":
        problemes.append(
            Warning(
                f"Moteur de sessions « {settings.SESSION_ENGINE} » : les applications "
                "doivent partager le même magasin de sessions.",
                hint="Conservez le moteur base de données, ou pointez toutes les applications vers le même Redis.",
                id=f"{IDENTIFIANT}.W002",
            )
        )

    origines = set(settings.CSRF_TRUSTED_ORIGINS)
    manquantes = [hote for hote in hotes if f"https://{hote}" not in origines]
    if manquantes and not settings.DEBUG:
        problemes.append(
            Warning(
                "Hôtes absents de CSRF_TRUSTED_ORIGINS : " + ", ".join(manquantes),
                hint="Les formulaires postés depuis ces applications seront refusés en 403.",
                id=f"{IDENTIFIANT}.W003",
            )
        )

    return problemes


@register(Tags.database)
def verifie_base_partagee(app_configs, **kwargs):
    """Un projet satellite ne doit pas être propriétaire du socle."""
    problemes = []
    if getattr(settings, "DR_URL_CONNEXION", "") and settings.DR_SOCLE_PROPRIETAIRE:
        problemes.append(
            Warning(
                "Ce projet délègue la connexion (DR_URL_CONNEXION) mais se déclare "
                "propriétaire du socle (DR_SOCLE_PROPRIETAIRE=1).",
                hint=(
                    "Un seul projet doit migrer les tables du socle. Passez "
                    "DR_SOCLE_PROPRIETAIRE=0 sur les applications satellites."
                ),
                id=f"{IDENTIFIANT}.W004",
            )
        )
    return problemes
