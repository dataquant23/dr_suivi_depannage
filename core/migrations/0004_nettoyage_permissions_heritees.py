"""
Supprime les permissions applicatives qui étaient portées par les modèles
métier (`recouvrement.reclamation`, `visite_client.visite`).

Elles sont désormais portées par `core.ApplicationMetier` afin de rester
disponibles même dans un projet qui n'installe pas l'application concernée.
Les groupes sont réalimentés juste après par le signal `post_migrate`.

Pas de dépendance sur les migrations `recouvrement`/`visite_client` : cette
opération filtre par `content_type__app_label` (une chaîne), elle ne touche
aucun modèle de ces apps et n'a donc pas besoin qu'elles soient installées.
Une dépendance explicite empêcherait tout projet satellite qui n'installe
que `core` de charger le graphe de migrations (`NodeNotFoundError`), ce qui
contredit le principe même du socle partagé (voir CONTEXTE_ECOSYSTEME_DRAN.md).
"""
from django.db import migrations

CODENAMES = [
    "acces_recouvrement",
    "importer_donnees",
    "exporter_donnees",
    "valider_reclamation",
    "gerer_sauvegardes",
    "acces_visite_client",
    "saisir_passage",
    "corriger_passage",
    "saisir_bilan_caisse",
    "acces_tableau_bord",
    "valider_plainte",
]


def supprime_permissions_heritees(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Permission.objects.filter(
        codename__in=CODENAMES,
        content_type__app_label__in=["recouvrement", "visite_client"],
    ).delete()


def sans_retour(apps, schema_editor):
    """Rien à restaurer : les permissions du socle couvrent les mêmes droits."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_applicationmetier"),
    ]

    operations = [migrations.RunPython(supprime_permissions_heritees, sans_retour)]
