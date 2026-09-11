"""
Crée une direction régionale et son référentiel de départ.

    python manage.py initialiser_direction --code DRAS --nom "Direction Régionale Abidjan Sud"
    python manage.py initialiser_direction --code DRAS --secteurs "Koumassi:051,Marcory:052"

Permet de déployer l'application pour une autre DR sans toucher au code.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Agence, DirectionRegionale, Secteur
from core.utils.files import racine


class Command(BaseCommand):
    help = "Crée une direction régionale, ses secteurs, ses agences et son arborescence de fichiers."

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True, help="Code court, ex. DRAS.")
        parser.add_argument("--nom", default="", help="Libellé complet de la direction.")
        parser.add_argument(
            "--code-secteur",
            default="",
            help="Code numérique de la direction dans l'espace des secteurs, ex. 040.",
        )
        parser.add_argument(
            "--secteurs",
            default="",
            help="Liste « Nom:code » séparée par des virgules, ex. \"Koumassi:051,Marcory:052\".",
        )
        parser.add_argument(
            "--sans-agences",
            action="store_true",
            help="Ne crée pas une agence par secteur.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        code = (options["code"] or "").strip().upper()
        if not code.isalnum():
            raise CommandError("Le code direction doit être alphanumérique (ex. DRAN, DRAS).")

        code_secteur = (options["code_secteur"] or "").strip().upper()
        direction, cree = DirectionRegionale.objects.get_or_create(
            code=code,
            defaults={"nom": options["nom"] or code, "code_secteur": code_secteur or "000"},
        )
        maj = []
        if not cree and options["nom"]:
            direction.nom = options["nom"]
            maj.append("nom")
        if not cree and code_secteur:
            direction.code_secteur = code_secteur
            maj.append("code_secteur")
        if maj:
            direction.save(update_fields=maj)

        self.stdout.write(
            self.style.SUCCESS(f"Direction {'créée' if cree else 'mise à jour'} : {direction}")
        )

        secteurs_crees = agences_creees = 0
        for entree in [s.strip() for s in options["secteurs"].split(",") if s.strip()]:
            if ":" not in entree:
                raise CommandError(f"Format attendu « Nom:code » — reçu : {entree!r}")
            nom, code_secteur = (partie.strip() for partie in entree.split(":", 1))

            _, nouveau = Secteur.objects.get_or_create(
                direction=direction, nom=nom, defaults={"code_secteur": code_secteur}
            )
            secteurs_crees += int(nouveau)

            if not options["sans_agences"]:
                _, nouvelle = Agence.objects.get_or_create(
                    direction=direction, nom=nom, defaults={"code_secteur": code_secteur}
                )
                agences_creees += int(nouvelle)

        # Arborescence de fichiers propre à la direction.
        for espace in ("impayes", "paiements", "sauvegardes", "archives", "bilan"):
            racine(espace, direction)

        self.stdout.write(f"  secteurs créés : {secteurs_crees}")
        self.stdout.write(f"  agences créées : {agences_creees}")
        self.stdout.write(f"  stockage       : {racine('impayes', direction).parent}")
