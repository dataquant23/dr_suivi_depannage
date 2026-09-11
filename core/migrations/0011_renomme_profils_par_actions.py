"""
Renomme les profils applicatifs vers des noms plus généraux, orientés
action, plutôt que des intitulés de poste :

  * recouvrement : « Responsable » -> « Gestion »
  * visite_client : « Agent terrain » -> « Saisie », « Encadrement » -> « Supervision »
  * coupure : « Gestionnaire » -> « Gestion »

Les droits associés ne changent pas — seul le libellé du profil dans
`core.AccesApplication.profil` (une chaîne, interprétée par le catalogue
Python de chaque application) est renommé.
"""
from __future__ import annotations

from django.db import migrations

RENOMMAGES = {
    "recouvrement": {"Responsable": "Gestion"},
    "visite_client": {"Agent terrain": "Saisie", "Encadrement": "Supervision"},
    "coupure": {"Gestionnaire": "Gestion"},
}


def renomme(apps, schema_editor):
    AccesApplication = apps.get_model("core", "AccesApplication")
    for code_application, correspondances in RENOMMAGES.items():
        for ancien, nouveau in correspondances.items():
            AccesApplication.objects.filter(
                application__code=code_application, profil=ancien
            ).update(profil=nouveau)


def renomme_arriere(apps, schema_editor):
    AccesApplication = apps.get_model("core", "AccesApplication")
    for code_application, correspondances in RENOMMAGES.items():
        for ancien, nouveau in correspondances.items():
            AccesApplication.objects.filter(
                application__code=code_application, profil=nouveau
            ).update(profil=ancien)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_backfill_acces_application"),
    ]

    operations = [migrations.RunPython(renomme, renomme_arriere)]
