import math
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from referentiel.models import (
    Equipement,
    ParametreDelai,
    Quartier,
    Secteur,
    Structure,
    TypeStructure,
)


class TypeIntervention(models.TextChoices):
    DEFINITIF = "DEFINITIF", "Définitif"
    PROVISOIRE = "PROVISOIRE", "Provisoire"


class CategorieProvisoire(models.TextChoices):
    COMPTEUR_SHUNTE = "COMPTEUR_SHUNTE", "Compteur shunté"
    SANS_ELECTRICITE = "SANS_ELECTRICITE", "Client sans électricité"
    AUTRE_EQUIPEMENT = "AUTRE_EQUIPEMENT", "Autre équipement"


class Statut(models.TextChoices):
    SAISI = "SAISI", "Saisi"
    EN_COURS = "EN_COURS", "En cours"
    REGULARISE = "REGULARISE", "Clôturé"
    CLOTURE = "CLOTURE", "Clôturé (définitif)"
    ARCHIVE = "ARCHIVE", "Archivé"


class EtatDelai(models.TextChoices):
    OK = "OK", "Dans les délais"
    BIENTOT = "BIENTOT", "Échéance proche"
    DEPASSE = "DEPASSE", "Délai dépassé"
    SANS_OBJET = "SANS_OBJET", "Sans objet"


class DepannageQuerySet(models.QuerySet):
    def en_cours(self):
        """Provisoires non encore clôturés."""
        return self.filter(
            type_intervention=TypeIntervention.PROVISOIRE,
            statut__in=[Statut.SAISI, Statut.EN_COURS],
        )

    def pour_utilisateur(self, user):
        """Restreint au perimetre du user connecte.

        Le rôle (est_admin/est_responsable) vit dans `core.AccesApplication`
        et le périmètre géographique (structure/secteurs) dans
        `referentiel.AffectationAgent` — voir `depannages.permissions`.
        """
        from depannages import permissions

        if permissions.est_admin(user):
            return self
        qs = self
        affectation = getattr(user, "affectation_depannage", None)
        structure_id = affectation.structure_id if affectation else None
        if structure_id:
            # Un dossier multi-structure remonte des deux cotes : il suffit
            # qu un equipement concerne la structure du user.
            qs = qs.filter(
                models.Q(structure_id=structure_id)
                | models.Q(equipements__structure_id=structure_id)
            ).distinct()
        if not permissions.est_responsable(user) and affectation and affectation.secteurs.exists():
            # Un dossier purement DC n a pas de secteur : il reste visible.
            qs = qs.filter(
                models.Q(secteur__in=affectation.secteurs.all()) | models.Q(secteur__isnull=True)
            )
        return qs


class Depannage(models.Model):
    """Fiche de suivi saisie depuis le terrain.

    Complete la fiche papier : on ne capte que l essentiel plus les preuves
    photo, en moins de deux minutes.
    """

    numero_bt = models.CharField("N BT / BTA", max_length=40, db_index=True)
    # Le secteur n est demande que si un equipement DR est concerne : un
    # dossier purement reseau (DC) n est pas rattache a un secteur clientele.
    secteur = models.ForeignKey(
        Secteur,
        on_delete=models.PROTECT,
        related_name="depannages",
        verbose_name="secteur",
        null=True,
        blank=True,
    )
    structure = models.ForeignKey(
        Structure, on_delete=models.PROTECT, related_name="depannages", verbose_name="structure"
    )
    type_intervention = models.CharField(
        "type d'intervention", max_length=12, choices=TypeIntervention.choices
    )
    categorie_provisoire = models.CharField(
        "catégorie du provisoire",
        max_length=20,
        choices=CategorieProvisoire.choices,
        blank=True,
    )
    equipements = models.ManyToManyField(
        Equipement, related_name="depannages", verbose_name="équipements concernés"
    )

    latitude = models.FloatField("latitude", null=True, blank=True)
    longitude = models.FloatField("longitude", null=True, blank=True)
    precision_m = models.FloatField("précision GPS (m)", null=True, blank=True)
    adresse_saisie = models.CharField("repérage / adresse", max_length=255, blank=True)

    # Deduits automatiquement de la position GPS (polygones OpenStreetMap).
    sous_quartier = models.ForeignKey(
        Quartier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="depannages_sous_quartier",
        verbose_name="sous-quartier",
    )
    quartier = models.ForeignKey(
        Quartier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="depannages",
        verbose_name="quartier",
    )
    commune = models.ForeignKey(
        Quartier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="depannages_commune",
        verbose_name="commune",
    )

    commentaire = models.TextField("commentaire", blank=True)
    statut = models.CharField(
        "statut", max_length=12, choices=Statut.choices, default=Statut.SAISI, db_index=True
    )

    # Delai fige a la creation : une modification du parametrage ne reecrit pas
    # l historique des dossiers deja ouverts, sauf choix explicite du responsable.
    delai_applique_heures = models.PositiveIntegerField(
        "délai appliqué (heures)", null=True, blank=True
    )

    date_saisie = models.DateTimeField("date de saisie", default=timezone.now, db_index=True)
    date_regularisation = models.DateTimeField(
        "date de clôture définitive", null=True, blank=True
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="depannages_crees",
        verbose_name="responsable d'ouverture",
    )
    synchronise = models.BooleanField("synchronisé", default=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    objects = DepannageQuerySet.as_manager()

    class Meta:
        verbose_name = "dépannage"
        verbose_name_plural = "dépannages"
        ordering = ["-date_saisie"]
        indexes = [
            models.Index(fields=["type_intervention", "statut"]),
            models.Index(fields=["categorie_provisoire"]),
        ]

    def __str__(self):
        return f"BT {self.numero_bt}"

    def get_absolute_url(self):
        return reverse("depannages:detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if self.type_intervention == TypeIntervention.DEFINITIF:
            self.categorie_provisoire = ""
        if self.est_provisoire and self.delai_applique_heures is None:
            self.delai_applique_heures = self.delai_reference()
        # Le quartier suit la position : on le recalcule des qu elle change.
        champs = kwargs.get("update_fields")
        if champs is None or {"latitude", "longitude"} & set(champs):
            self.rattacher_zone(sauvegarder=False)
            if champs is not None:
                kwargs["update_fields"] = list(
                    set(champs) | {"sous_quartier", "quartier", "commune"}
                )
        super().save(*args, **kwargs)

    def rattacher_zone(self, sauvegarder=True):
        """Deduit le sous-quartier, le quartier et la commune de la position GPS."""
        if not self.a_position:
            return None, None, None
        sous_quartier, quartier, commune = Quartier.localiser_complet(
            self.latitude, self.longitude
        )
        self.sous_quartier = sous_quartier
        self.quartier = quartier
        self.commune = commune
        if sauvegarder:
            super().save(
                update_fields=["sous_quartier", "quartier", "commune", "modifie_le"]
            )
        return sous_quartier, quartier, commune

    @property
    def zone_libelle(self):
        """Libellé le plus précis disponible : sous-quartier, quartier, commune, secteur."""
        if self.sous_quartier_id:
            return self.sous_quartier.nom
        if self.quartier_id:
            return self.quartier.nom
        if self.commune_id:
            return self.commune.nom
        if self.secteur_id:
            return self.secteur.libelle
        return "Zone inconnue"

    # --- Etat du dossier -------------------------------------------------

    @property
    def est_provisoire(self):
        return self.type_intervention == TypeIntervention.PROVISOIRE

    @property
    def est_ouvert(self):
        return self.est_provisoire and self.statut in {Statut.SAISI, Statut.EN_COURS}

    @property
    def est_shunte(self):
        return self.categorie_provisoire == CategorieProvisoire.COMPTEUR_SHUNTE

    def delai_reference(self, parametres=None):
        """Délai applicable en heures selon la catégorie du provisoire."""
        if not self.est_provisoire:
            return None
        p = parametres or ParametreDelai.actuel()
        return {
            CategorieProvisoire.COMPTEUR_SHUNTE: p.delai_compteur_shunte,
            CategorieProvisoire.SANS_ELECTRICITE: p.delai_sans_electricite,
            CategorieProvisoire.AUTRE_EQUIPEMENT: p.delai_autre_equipement,
        }.get(self.categorie_provisoire, p.delai_autre_equipement)

    @property
    def echeance(self):
        if not self.est_provisoire or not self.delai_applique_heures:
            return None
        return self.date_saisie + timedelta(hours=self.delai_applique_heures)

    @property
    def heures_ecoulees(self):
        """Temps écoulé entre la saisie et la clôture définitive (ou
        maintenant si pas encore clôturé). Valable aussi bien pour un
        dossier provisoire que définitif : un dossier définitif multi-
        structure peut lui aussi rester en attente de clôture (cf.
        `cloture_en_attente`) et accumuler un délai réel avant que toutes
        les structures aient traité leur part."""
        fin = self.date_regularisation or timezone.now()
        return (fin - self.date_saisie).total_seconds() / 3600

    @property
    def heures_restantes(self):
        if not self.echeance or not self.est_ouvert:
            return None
        return (self.echeance - timezone.now()).total_seconds() / 3600

    @property
    def etat_delai(self):
        """OK (sous le seuil), BIENTOT (seuil a 100%), DEPASSE (au dela)."""
        if not self.est_ouvert or not self.delai_applique_heures:
            return EtatDelai.SANS_OBJET
        consomme = (self.heures_ecoulees / self.delai_applique_heures) * 100
        if consomme >= 100:
            return EtatDelai.DEPASSE
        if consomme >= ParametreDelai.actuel().seuil_alerte_pct:
            return EtatDelai.BIENTOT
        return EtatDelai.OK

    @property
    def pourcentage_delai(self):
        if not self.est_ouvert or not self.delai_applique_heures:
            return 0
        return min(round((self.heures_ecoulees / self.delai_applique_heures) * 100), 100)

    @property
    def retard_heures(self):
        """Nombre d'heures au-delà de l'échéance, 0 si dans les temps."""
        if not self.est_ouvert or not self.delai_applique_heures:
            return 0
        depassement = self.heures_ecoulees - self.delai_applique_heures
        return max(round(depassement), 0)

    # --- Multi-structure et clôture --------------------------------------

    @property
    def structures_concernees(self):
        """Structures responsables des équipements cochés.

        Un dossier peut concerner une DR et une DC : il apparaît alors dans les
        deux files et ne sera définitif qu'une fois clôturé des deux côtés.
        """
        vues, resultat = set(), []
        for equipement in self.equipements.all():
            if equipement.structure_id not in vues:
                vues.add(equipement.structure_id)
                resultat.append(equipement.structure)
        # DR (reseau, ex. DRAN) avant DC (clientele, ex. DCRD) : un tri par
        # chaine ("DC" < "DR") donnerait l ordre inverse.
        return sorted(
            resultat, key=lambda s: (s.type_structure != TypeStructure.DR, s.code)
        )

    @property
    def est_multi_structure(self):
        return len(self.structures_concernees) > 1

    @property
    def concerne_dr(self):
        return any(s.type_structure == TypeStructure.DR for s in self.structures_concernees)

    @property
    def structures_cloturees(self):
        return {cloture.structure_id for cloture in self.clotures.all()}

    def est_cloture_pour(self, structure):
        return structure.pk in self.structures_cloturees

    @property
    def structures_restantes(self):
        cloturees = self.structures_cloturees
        return [s for s in self.structures_concernees if s.pk not in cloturees]

    @property
    def progression_cloture(self):
        """(nombre de structures clôturées, nombre total) pour l'affichage."""
        return len(self.structures_cloturees), len(self.structures_concernees)

    @property
    def cloture_en_attente(self):
        """Vrai s'il reste au moins une structure qui n'a pas clôturé sa part.

        À ne pas confondre avec `est_ouvert`, qui ne reflète que le statut
        provisoire (SAISI/EN_COURS) : un dossier DÉFINITIF n'est jamais
        "provisoire" donc `est_ouvert` y vaut toujours False, même si une
        structure n'a pas encore clôturé sa part. Cette propriété-ci sert au
        workflow de clôture proprement dit (bouton Clôturer, avancement),
        valable aussi bien pour un dossier provisoire que définitif.
        """
        return bool(self.structures_restantes)

    def structures_cloturables_par(self, utilisateur):
        """Structures dont cet utilisateur peut clôturer la part.

        Le dépanneur traite le périmètre DR, l'agent DCRD le périmètre DC ;
        responsables et administrateurs peuvent clôturer les deux.
        """
        from depannages import permissions

        restantes = self.structures_restantes
        if permissions.est_responsable(utilisateur):
            return restantes
        if permissions.est_agent_dcrd(utilisateur):
            return [s for s in restantes if s.type_structure == TypeStructure.DC]
        return [s for s in restantes if s.type_structure == TypeStructure.DR]

    def cloturer_structure(self, structure, utilisateur, commentaire=""):
        """Enregistre la clôture de la part d'une structure.

        Le dossier ne devient définitif que lorsque toutes les structures
        concernées ont clôturé leur part.
        """
        cloture, cree = ClotureStructure.objects.get_or_create(
            depannage=self,
            structure=structure,
            defaults={"cloture_par": utilisateur, "commentaire": commentaire},
        )
        if not cree:
            return cloture, False

        ancien = self.statut
        HistoriqueStatut.objects.create(
            depannage=self,
            statut_avant=ancien,
            statut_apres=self.statut,
            action=f"Clôture de la part {structure.code}",
            utilisateur=utilisateur,
            commentaire=commentaire,
        )

        # Toutes les parts sont traitées : le dossier passe en définitif.
        if not self.structures_restantes:
            self.statut = Statut.CLOTURE
            self.date_regularisation = timezone.now()
            self.save(update_fields=["statut", "date_regularisation", "modifie_le"])
            HistoriqueStatut.objects.create(
                depannage=self,
                statut_avant=ancien,
                statut_apres=self.statut,
                action="Clôture définitive du dépannage",
                utilisateur=utilisateur,
            )
        elif self.statut == Statut.SAISI:
            self.statut = Statut.EN_COURS
            self.save(update_fields=["statut", "modifie_le"])

        return cloture, True

    # --- Géolocalisation -------------------------------------------------

    @property
    def a_position(self):
        return self.latitude is not None and self.longitude is not None

    def distance_km(self, lat, lon):
        """Distance a vol d oiseau (formule de haversine), en kilometres."""
        if not self.a_position or lat is None or lon is None:
            return None
        rayon_terre = 6371.0
        dlat = math.radians(lat - self.latitude)
        dlon = math.radians(lon - self.longitude)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(self.latitude))
            * math.cos(math.radians(lat))
            * math.sin(dlon / 2) ** 2
        )
        return rayon_terre * 2 * math.asin(math.sqrt(a))

    @property
    def url_maps(self):
        """Itinéraire Google Maps : application native si installée, sinon web."""
        if not self.a_position:
            return None
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&destination={self.latitude},{self.longitude}&travelmode=driving"
        )

    @property
    def url_waze(self):
        if not self.a_position:
            return None
        return f"https://waze.com/ul?ll={self.latitude},{self.longitude}&navigate=yes"

    @property
    def url_plans(self):
        """Plans (iOS) ; le schema maps: est repris par l application Apple."""
        if not self.a_position:
            return None
        return f"https://maps.apple.com/?daddr={self.latitude},{self.longitude}&dirflg=d"

    @property
    def urls_navigation(self):
        """Toutes les applications de navigation proposees au depanneur."""
        if not self.a_position:
            return []
        return [
            {"nom": "Google Maps", "url": self.url_maps, "icone": "maps"},
            {"nom": "Waze", "url": self.url_waze, "icone": "waze"},
            {"nom": "Plans", "url": self.url_plans, "icone": "plans"},
        ]


class ClotureStructure(models.Model):
    """Clôture de la part d'une structure sur un dépannage provisoire.

    Conserve le responsable de clôture, en regard du responsable d'ouverture
    porte par `Depannage.cree_par`.
    """

    depannage = models.ForeignKey(
        Depannage, on_delete=models.CASCADE, related_name="clotures"
    )
    structure = models.ForeignKey(
        Structure, on_delete=models.PROTECT, related_name="clotures"
    )
    cloture_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="clotures_realisees",
        verbose_name="responsable de clôture",
    )
    date_cloture = models.DateTimeField("date de clôture", auto_now_add=True)
    commentaire = models.TextField("commentaire de clôture", blank=True)

    class Meta:
        verbose_name = "clôture par structure"
        verbose_name_plural = "clôtures par structure"
        ordering = ["date_cloture"]
        unique_together = [("depannage", "structure")]

    def __str__(self):
        return f"{self.depannage} - {self.structure.code}"


class TypePhoto(models.TextChoices):
    OUVRAGE = "OUVRAGE", "Photo de l'ouvrage"
    FICHE_AVIS = "FICHE_AVIS", "Photo de la fiche d'avis"
    BON_DEPANNAGE = "BON_DEPANNAGE", "Bon de dépannage (clôture)"
    EQUIPEMENT_CLOTURE = "EQUIP_CLOT", "Photo équipement (clôture)"


class OriginePhoto(models.TextChoices):
    CAMERA = "CAMERA", "Prise dans l'application"
    GALERIE = "GALERIE", "Fichier joint"


def chemin_photo(instance, nom_fichier):
    d = instance.depannage.date_saisie
    return (
        f"depannages/{d:%Y/%m}/{instance.depannage_id}/"
        f"{instance.type_photo.lower()}_{nom_fichier}"
    )


class PhotoDepannage(models.Model):
    depannage = models.ForeignKey(
        Depannage, on_delete=models.CASCADE, related_name="photos"
    )
    # Renseigne pour les pièces jointes à une clôture de structure.
    cloture = models.ForeignKey(
        ClotureStructure,
        on_delete=models.CASCADE,
        related_name="photos",
        null=True,
        blank=True,
    )
    type_photo = models.CharField("type", max_length=14, choices=TypePhoto.choices)
    origine = models.CharField(
        "origine", max_length=8, choices=OriginePhoto.choices, default=OriginePhoto.CAMERA
    )
    image = models.ImageField("image", upload_to=chemin_photo)
    ajoutee_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "photo"
        verbose_name_plural = "photos"
        ordering = ["type_photo", "ajoutee_le"]

    def __str__(self):
        return f"{self.get_type_photo_display()} - BT {self.depannage.numero_bt}"


class HistoriqueStatut(models.Model):
    """Trace automatique : date, utilisateur, action, statut avant/après."""

    depannage = models.ForeignKey(
        Depannage, on_delete=models.CASCADE, related_name="historique"
    )
    statut_avant = models.CharField("statut avant", max_length=12, blank=True)
    statut_apres = models.CharField("statut après", max_length=12)
    action = models.CharField("action", max_length=150)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    commentaire = models.TextField("commentaire", blank=True)
    horodatage = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "historique"
        verbose_name_plural = "historique"
        ordering = ["-horodatage"]

    def __str__(self):
        return f"{self.depannage} : {self.statut_avant} -> {self.statut_apres}"
