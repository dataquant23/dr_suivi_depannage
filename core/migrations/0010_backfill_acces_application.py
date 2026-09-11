"""
Backfill des accès applicatifs existants après le passage des droits
partagés (`core.profils.PROFILS`) à un accès + profil propre à chaque
application (`core.AccesApplication`).

Reproduit exactement le comportement actuel : un agent Direction régionale
ou Responsable commercial avait accès à tout (recouvrement + visite_client +
coupure) ; les autres profils n'avaient que la visite client. Zéro
régression pour les agents déjà en place — voir le plan « Accès et profils
par application ».
"""
from __future__ import annotations

from django.db import migrations

ROLES_ENCADREMENT = {"Direction régionale", "Responsable commercial"}
ROLES_TERRAIN = {"Litige et recouvrement", "Conseiller clientèle", "Caisse"}


def backfill(apps, schema_editor):
    Agent = apps.get_model("core", "Agent")
    Group = apps.get_model("auth", "Group")
    ApplicationMetier = apps.get_model("core", "ApplicationMetier")
    AccesApplication = apps.get_model("core", "AccesApplication")

    # `core.profils.APPLICATIONS` alimente déjà ces lignes via le signal
    # `post_migrate` de `visite_client` — mais celui-ci se déclenche APRÈS
    # cette migration de données dans le même `migrate`. On les crée donc
    # ici si besoin, pour ne pas dépendre de l'ordre d'exécution.
    definitions = {
        "recouvrement": "Rétablissement / recouvrement client",
        "visite_client": "Visite client",
        "coupure": "Coupure — Éligibilité coupure",
    }
    applications = {}
    for code, nom in definitions.items():
        application, _ = ApplicationMetier.objects.get_or_create(code=code, defaults={"nom": nom})
        applications[code] = application

    for agent in Agent.objects.prefetch_related("groups"):
        role = agent.groups.values_list("name", flat=True).first()
        if not role:
            continue

        if role in ROLES_ENCADREMENT:
            AccesApplication.objects.update_or_create(
                agent=agent, application=applications["recouvrement"],
                defaults={"profil": "Responsable", "actif": True},
            )
            AccesApplication.objects.update_or_create(
                agent=agent, application=applications["visite_client"],
                defaults={"profil": "Encadrement", "actif": True},
            )
            AccesApplication.objects.update_or_create(
                agent=agent, application=applications["coupure"],
                defaults={"profil": "Gestionnaire", "actif": True},
            )
        elif role in ROLES_TERRAIN:
            AccesApplication.objects.update_or_create(
                agent=agent, application=applications["visite_client"],
                defaults={"profil": "Agent terrain", "actif": True},
            )


def sans_retour(apps, schema_editor):
    """Rien à restaurer : les profils organisationnels (groupes) couvrent les mêmes droits."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_alter_applicationmetier_options_accesapplication"),
    ]

    operations = [migrations.RunPython(backfill, sans_retour)]
