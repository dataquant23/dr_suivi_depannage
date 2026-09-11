"""
État de l'installation : base, directions, applications, profils.

    python manage.py diagnostic

À lancer après chaque déploiement, en particulier après la bascule vers
PostgreSQL ou l'ajout d'une application sur la base partagée.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import connection

from core.models import ApplicationMetier, DirectionRegionale
from core.profils import APPLICATIONS, PROFILS


class Command(BaseCommand):
    help = "Affiche l'état de l'installation (base, directions, applications, profils, droits)."

    def handle(self, *args, **options):
        self._section("Base de données")
        moteur = connection.vendor
        self.stdout.write(f"  moteur                : {moteur}")
        self.stdout.write(f"  nom                   : {settings.DATABASES['default']['NAME']}")
        self.stdout.write(
            f"  propriétaire du socle : {'oui' if settings.DR_SOCLE_PROPRIETAIRE else 'non (projet satellite)'}"
        )
        if moteur == "sqlite":
            self.stdout.write(
                self.style.WARNING(
                    "  SQLite : écritures sérialisées et `SELECT … FOR UPDATE` inopérant.\n"
                    "  PostgreSQL est requis dès que plusieurs applications écrivent en parallèle."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("  Verrous de compteurs actifs (SELECT … FOR UPDATE)."))

        self._section("Directions régionales")
        for direction in DirectionRegionale.objects.all():
            agents = direction.agents.count()
            secteurs = direction.core_secteurs.count()
            etat = "active" if direction.actif else "inactive"
            self.stdout.write(f"  {direction.code:<8} {direction.nom:<45} {secteurs} secteur(s), {agents} agent(s) [{etat}]")

        self._section("Applications déclarées")
        installees = set(settings.INSTALLED_APPS)
        for application in ApplicationMetier.objects.all():
            presente = any(app.split(".")[0] == application.code for app in installees)
            marque = "installée ici" if presente else "déployée ailleurs"
            self.stdout.write(f"  {application.code:<16} {application.nom:<45} ({marque})")
        manquantes = set(APPLICATIONS) - set(ApplicationMetier.objects.values_list("code", flat=True))
        if manquantes:
            self.stdout.write(self.style.WARNING(f"  Registre incomplet : {', '.join(sorted(manquantes))}"))

        self._section("Profils et droits")
        for nom in PROFILS:
            groupe = Group.objects.filter(name=nom).first()
            if groupe is None:
                self.stdout.write(self.style.WARNING(f"  {nom:<26} ABSENT — lancez initialiser_profils"))
                continue
            self.stdout.write(
                f"  {nom:<26} {groupe.permissions.count():>2} permission(s), "
                f"{groupe.user_set.count():>3} agent(s)"
            )

        self._section("Contrôles")
        egarees = Permission.objects.filter(
            codename__in=[p.split(".", 1)[1] for d in APPLICATIONS.values() for p in d["permissions"]]
        ).exclude(content_type__app_label="core")
        if egarees.exists():
            self.stdout.write(
                self.style.ERROR(
                    "  Des permissions applicatives sont accrochées hors du socle : "
                    + ", ".join(f"{p.content_type.app_label}.{p.codename}" for p in egarees)
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("  Toutes les permissions applicatives sont portées par le socle."))

        Agent = get_user_model()
        sans_profil = Agent.objects.filter(groups__isnull=True, is_superuser=False).count()
        if sans_profil:
            self.stdout.write(self.style.WARNING(f"  {sans_profil} agent(s) sans profil (aucun droit)."))
        else:
            self.stdout.write(self.style.SUCCESS("  Tous les agents sont rattachés à un profil."))

    def _section(self, titre: str) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(titre))
