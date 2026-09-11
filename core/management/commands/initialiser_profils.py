"""
Crée / met à jour les profils métier et leurs droits, puis rattache les agents.

    python manage.py initialiser_profils
    python manage.py initialiser_profils --reaffecter   # force le recalcul des profils

La matrice des droits est déclarée dans `core/profils.py`.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core.profils import PROFILS, profil_pour_fonction
from core.services.droits import affecte_profils_automatiquement, synchronise_profils


class Command(BaseCommand):
    help = "Synchronise les profils (groupes) et rattache les agents selon leur fonction."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reaffecter",
            action="store_true",
            help="Réaffecte tous les agents, y compris ceux déjà rattachés à un profil.",
        )
        parser.add_argument(
            "--sans-agents",
            action="store_true",
            help="Se limite à la création des groupes et des permissions.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        resume = synchronise_profils(verbeux=True)
        for profil, nombre in resume.items():
            self.stdout.write(f"  {profil:<26} {nombre} permission(s)")

        if options["sans_agents"]:
            self.stdout.write(self.style.SUCCESS("Profils synchronisés."))
            return

        Agent = get_user_model()
        if options["reaffecter"]:
            compteur: dict[str, int] = {}
            for agent in Agent.objects.all():
                profil = profil_pour_fonction(agent.fonction)
                agent.affecter_profil(profil)
                compteur[profil] = compteur.get(profil, 0) + 1
        else:
            compteur = affecte_profils_automatiquement()

        self.stdout.write("")
        for profil, nombre in sorted(compteur.items()):
            self.stdout.write(f"  {profil:<26} {nombre} agent(s)")

        non_rattaches = Agent.objects.filter(groups__isnull=True).count()
        if non_rattaches:
            self.stdout.write(
                self.style.WARNING(f"  {non_rattaches} agent(s) sans profil (compte technique ?)")
            )
        self.stdout.write(self.style.SUCCESS("Profils et rattachements à jour."))
