"""Recalcule le quartier et la commune des depannages deja enregistres.

    python manage.py rattacher_depannages
    python manage.py rattacher_depannages --tous   # y compris ceux deja rattaches
"""

from django.core.management.base import BaseCommand

from depannages.models import Depannage


class Command(BaseCommand):
    help = "Rattache les depannages existants a leur quartier et commune."

    def add_arguments(self, parseur):
        parseur.add_argument(
            "--tous",
            action="store_true",
            help="Recalcule aussi les dossiers deja rattaches.",
        )

    def handle(self, *args, **options):
        dossiers = Depannage.objects.filter(
            latitude__isnull=False, longitude__isnull=False
        )
        if not options["tous"]:
            dossiers = dossiers.filter(quartier__isnull=True)

        total = dossiers.count()
        self.stdout.write(f"{total} dossier(s) a traiter...")

        rattaches = avec_sous_quartier = sans_zone = 0
        for dossier in dossiers.iterator(chunk_size=200):
            sous_quartier, quartier, commune = dossier.rattacher_zone(sauvegarder=True)
            if sous_quartier or quartier or commune:
                rattaches += 1
                if sous_quartier:
                    avec_sous_quartier += 1
            else:
                sans_zone += 1

        self.stdout.write(self.style.SUCCESS("Rattachement termine."))
        self.stdout.write(f"  Rattaches              : {rattaches}")
        self.stdout.write(f"  Dont avec sous-quartier: {avec_sous_quartier}")
        self.stdout.write(f"  Hors des zones         : {sans_zone}")
