"""Initialise le referentiel et, en option, un jeu de demonstration.

    python manage.py initialiser            # referentiel seul
    python manage.py initialiser --demo     # + comptes et dossiers d exemple
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from django.contrib.auth import get_user_model

from referentiel.models import (
    AffectationAgent,
    Equipement,
    ParametreDelai,
    Secteur,
    Structure,
    TypeStructure,
)

Agent = get_user_model()

# Equipements repris de la liste fournie (liste_des_equipements.docx).
EQUIPEMENTS_DR = [
    ("Compteur", "Compteur"),
    ("CCA / Coffret à fusibles", "Enveloppe"),
    ("Tableau", "Tableau"),
    ("Cahors", "Réseau"),
    ("Grille", "Enveloppe"),
    ("Potelet", "Réseau"),
    ("Raccord brûlé", "Réseau"),
    ("Branchement", "Branchement"),
    ("Scellé", "Accessoire"),
    ("Disjoncteur", "Protection"),
]

EQUIPEMENTS_DC = [
    ("TFO", "Transformateur"),
    ("TUR", "Réseau"),
    ("Liaison TFO TUR", "Réseau"),
    ("Sortie poste", "Poste"),
    ("Borne de lotissement", "Réseau"),
    ("IACM", "Protection"),
    ("Fusion fusibles", "Protection"),
]

# Secteurs gérés par la DRAN. Codes 041-043 confirmés ; 044-046 provisoires
# (Deux Plateaux, Djibi, Bingerville). Abobo et Anyama exclus (hors DRAN).
SECTEURS = [
    # OSM ne subdivise pas la commune d Adjame : legere separation manuelle
    # nord/sud autour du centre reel pour distinguer les deux secteurs.
    ("041", "ADJAME NORD", 5.3740, -4.0197),
    ("042", "ADJAME SUD", 5.3636, -4.0197),
    ("043", "COCODY", 5.3823, -3.9650),
    ("044", "DEUX PLATEAUX", 5.3717, -3.9933),
    ("045", "DJIBI", 5.4224, -3.9816),
    ("046", "BINGERVILLE", 5.3484, -3.8255),
]


class Command(BaseCommand):
    help = "Initialise le referentiel (structures, secteurs, equipements, delais)."

    def add_arguments(self, parseur):
        parseur.add_argument(
            "--demo",
            action="store_true",
            help="Cree aussi des comptes et des dossiers de demonstration.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dran, _ = Structure.objects.get_or_create(
            code="DRAN",
            defaults={
                "libelle": "Direction Régionale Abidjan Nord",
                "type_structure": TypeStructure.DR,
            },
        )
        dcrd, _ = Structure.objects.get_or_create(
            code="DCRD",
            defaults={
                "libelle": "Direction Centrale Réseau Distribution",
                "type_structure": TypeStructure.DC,
            },
        )

        for libelle, categorie in EQUIPEMENTS_DR:
            Equipement.objects.get_or_create(
                structure=dran, libelle=libelle, defaults={"categorie": categorie}
            )
        for libelle, categorie in EQUIPEMENTS_DC:
            Equipement.objects.get_or_create(
                structure=dcrd, libelle=libelle, defaults={"categorie": categorie}
            )

        for code, libelle, latitude, longitude in SECTEURS:
            Secteur.objects.get_or_create(
                code=code,
                defaults={
                    "libelle": libelle,
                    "structure": dran,
                    "latitude": latitude,
                    "longitude": longitude,
                },
            )

        parametres = ParametreDelai.actuel()
        self.stdout.write(self.style.SUCCESS("Referentiel initialise."))
        self.stdout.write(f"  Structures  : {Structure.objects.count()}")
        self.stdout.write(f"  Secteurs    : {Secteur.objects.count()}")
        self.stdout.write(f"  Equipements : {Equipement.objects.count()}")
        self.stdout.write(f"  Delais      : {parametres}")

        if options["demo"]:
            self._creer_demo(dran, parametres)

    def _creer_demo(self, structure, parametres):
        from depannages.models import (
            CategorieProvisoire,
            Depannage,
            HistoriqueStatut,
            Statut,
            TypeIntervention,
        )

        from core.services.acces import definir_acces

        comptes = [
            ("admin", "Habib", "ADJAGBA", "Administration", True),
            ("responsable", "Marie", "DUPONT", "Responsable", False),
            ("depanneur", "Amine", "KOUAME", "Dépanneur", False),
            ("agentdcrd", "Sekou", "TRAORE", "Agent DCRD", False),
        ]
        crees = []
        for matricule, prenom, nom, profil, superuser in comptes:
            agent, nouveau = Agent.objects.get_or_create(
                matricule=matricule,
                defaults={
                    "prenoms": prenom,
                    "nom": nom,
                    "is_staff": superuser,
                    "is_superuser": superuser,
                },
            )
            if nouveau:
                agent.set_password("depannage2026")
                agent.save()
            AffectationAgent.objects.get_or_create(agent=agent, defaults={"structure": structure})
            definir_acces(agent, "depannages", profil, True)
            crees.append((agent, profil))

        depanneur = Agent.objects.get(matricule="depanneur")
        secteurs = list(Secteur.objects.all())
        equipements = list(Equipement.objects.all())
        maintenant = timezone.now()

        if Depannage.objects.exists():
            self.stdout.write(self.style.WARNING("Dossiers deja presents : demo ignoree."))
        else:
            categories = [
                (CategorieProvisoire.COMPTEUR_SHUNTE, 8),
                (CategorieProvisoire.SANS_ELECTRICITE, 11),
                (CategorieProvisoire.AUTRE_EQUIPEMENT, 9),
            ]
            numero = 24600
            for categorie, quantite in categories:
                for _ in range(quantite):
                    numero += random.randint(1, 9)
                    secteur = random.choice(secteurs)
                    # Anciennete variee pour obtenir des dossiers OK, proches et depasses.
                    heures = random.choice([2, 6, 14, 22, 26, 33, 45, 52, 61])
                    depannage = Depannage.objects.create(
                        numero_bt=str(numero),
                        secteur=secteur,
                        structure=structure,
                        type_intervention=TypeIntervention.PROVISOIRE,
                        categorie_provisoire=categorie,
                        latitude=secteur.latitude + random.uniform(-0.008, 0.008),
                        longitude=secteur.longitude + random.uniform(-0.008, 0.008),
                        precision_m=random.randint(5, 30),
                        adresse_saisie=f"Carrefour {random.randint(1, 40)}, {secteur.libelle}",
                        commentaire="Intervention provisoire, regularisation a programmer.",
                        statut=Statut.EN_COURS,
                        date_saisie=maintenant - timedelta(hours=heures),
                        cree_par=depanneur,
                    )
                    depannage.equipements.set(random.sample(equipements, random.randint(1, 3)))
                    HistoriqueStatut.objects.create(
                        depannage=depannage,
                        statut_apres=Statut.EN_COURS,
                        action="Creation de la fiche",
                        utilisateur=depanneur,
                    )

            # Quelques definitifs et regularises pour alimenter le recapitulatif.
            for _ in range(18):
                numero += random.randint(1, 9)
                secteur = random.choice(secteurs)
                jours = random.randint(1, 25)
                depannage = Depannage.objects.create(
                    numero_bt=str(numero),
                    secteur=secteur,
                    structure=structure,
                    type_intervention=TypeIntervention.DEFINITIF,
                    latitude=secteur.latitude + random.uniform(-0.008, 0.008),
                    longitude=secteur.longitude + random.uniform(-0.008, 0.008),
                    commentaire="Depannage definitif realise sur place.",
                    statut=Statut.CLOTURE,
                    date_saisie=maintenant - timedelta(days=jours),
                    date_regularisation=maintenant - timedelta(days=jours),
                    cree_par=depanneur,
                )
                depannage.equipements.set(random.sample(equipements, random.randint(1, 2)))

            for _ in range(12):
                numero += random.randint(1, 9)
                secteur = random.choice(secteurs)
                jours = random.randint(2, 20)
                duree = random.randint(8, 60)
                depannage = Depannage.objects.create(
                    numero_bt=str(numero),
                    secteur=secteur,
                    structure=structure,
                    type_intervention=TypeIntervention.PROVISOIRE,
                    categorie_provisoire=random.choice(CategorieProvisoire.values),
                    latitude=secteur.latitude + random.uniform(-0.008, 0.008),
                    longitude=secteur.longitude + random.uniform(-0.008, 0.008),
                    statut=Statut.REGULARISE,
                    date_saisie=maintenant - timedelta(days=jours),
                    date_regularisation=maintenant - timedelta(days=jours) + timedelta(hours=duree),
                    cree_par=depanneur,
                )
                depannage.equipements.set(random.sample(equipements, 1))

        self.stdout.write(self.style.SUCCESS("\nDonnees de demonstration creees."))
        self.stdout.write(f"  Dossiers : {Depannage.objects.count()}")
        self.stdout.write("\n  Comptes (mot de passe : depannage2026)")
        for agent, profil in crees:
            self.stdout.write(f"    {agent.matricule:12} {profil}")
