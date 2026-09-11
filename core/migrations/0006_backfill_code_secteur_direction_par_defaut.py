"""
Renseigne le code numérique de la direction créée par défaut (0002).

Sans cette passe, les installations existantes gardent `code_secteur="000"`
pour leur direction initiale (le champ vient d'être ajouté) : ce n'est
correct que pour les nouvelles installations créées après ce changement.
"""
from django.conf import settings
from django.db import migrations


def renseigne_code_secteur(apps, schema_editor):
    DirectionRegionale = apps.get_model("core", "DirectionRegionale")
    DirectionRegionale.objects.filter(
        code=settings.DR_CODE_DEFAUT, code_secteur="000"
    ).update(code_secteur=settings.DR_CODE_SECTEUR_DEFAUT)


def revert_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("core", "0005_directionregionale_code_secteur")]

    operations = [migrations.RunPython(renseigne_code_secteur, revert_noop)]
