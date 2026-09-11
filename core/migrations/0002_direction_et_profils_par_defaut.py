"""
Crée la direction régionale initiale.

Les profils (groupes + permissions) sont synchronisés après chaque `migrate`
par le signal `post_migrate` de `core.apps.CoreConfig` : à ce moment-là, les
permissions des nouveaux modèles existent réellement en base.
"""
from django.conf import settings
from django.db import migrations


def cree_direction_par_defaut(apps, schema_editor):
    DirectionRegionale = apps.get_model("core", "DirectionRegionale")
    DirectionRegionale.objects.get_or_create(
        code=settings.DR_CODE_DEFAUT, defaults={"nom": settings.DR_NOM_DEFAUT}
    )


def supprime_direction_par_defaut(apps, schema_editor):
    DirectionRegionale = apps.get_model("core", "DirectionRegionale")
    DirectionRegionale.objects.filter(code=settings.DR_CODE_DEFAUT).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [migrations.RunPython(cree_direction_par_defaut, supprime_direction_par_defaut)]
