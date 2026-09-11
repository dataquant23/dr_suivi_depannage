import math

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class TypeStructure(models.TextChoices):
    DR = "DR", "Direction Régionale"
    DC = "DC", "Direction Centrale"


class Structure(models.Model):
    """DRAN, DCRD, et toute autre DR/DC ajoutée plus tard.

    Le référentiel n'est jamais codé en dur : l'administrateur ajoute les
    structures et leurs équipements depuis l'application.
    """

    code = models.CharField("code", max_length=20, unique=True)
    libelle = models.CharField("libellé", max_length=150)
    type_structure = models.CharField(
        "type", max_length=2, choices=TypeStructure.choices, default=TypeStructure.DR
    )
    actif = models.BooleanField("actif", default=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    # Correspondance de valeur (pas une FK) vers core.DirectionRegionale.code ;
    # les deux référentiels géographiques restent séparés.
    code_direction_dran = models.CharField(
        "code direction régionale (socle DRAN)",
        max_length=20,
        blank=True,
        help_text="Code de la DirectionRegionale correspondante côté django_dran, si applicable.",
    )

    class Meta:
        verbose_name = "structure"
        verbose_name_plural = "structures"
        # "-type_structure" place DR avant DC (réseau avant clientèle).
        ordering = ["-type_structure", "code"]

    def __str__(self):
        return self.code


class Secteur(models.Model):
    """Zone géographique de rattachement d'un dépannage."""

    code = models.CharField("code", max_length=30, unique=True)
    libelle = models.CharField("libellé", max_length=150)
    structure = models.ForeignKey(
        Structure, on_delete=models.PROTECT, related_name="secteurs", verbose_name="structure"
    )
    # Centre approximatif du secteur, utilisé pour centrer la carte.
    latitude = models.FloatField("latitude", null=True, blank=True)
    longitude = models.FloatField("longitude", null=True, blank=True)
    actif = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "secteur"
        verbose_name_plural = "secteurs"
        ordering = ["libelle"]

    def __str__(self):
        return self.libelle


class Equipement(models.Model):
    """Équipement cochable, rattaché à la structure qui en est responsable."""

    libelle = models.CharField("libellé", max_length=150)
    code = models.CharField("code", max_length=40, blank=True)
    categorie = models.CharField("catégorie", max_length=80, blank=True)
    structure = models.ForeignKey(
        Structure, on_delete=models.CASCADE, related_name="equipements", verbose_name="structure"
    )
    actif = models.BooleanField("actif", default=True)

    class Meta:
        verbose_name = "équipement"
        verbose_name_plural = "équipements"
        # Meme logique que Structure.Meta.ordering : le perimetre reseau
        # (DR/DRAN) doit apparaitre avant le perimetre clientele (DC/DCRD).
        ordering = ["-structure__type_structure", "structure__code", "libelle"]
        unique_together = [("structure", "libelle")]

    def __str__(self):
        return f"{self.structure.code} - {self.libelle}"


class ParametreDelai(models.Model):
    """Délais de traitement des provisoires, modifiables par le responsable.

    Une seule ligne active est utilisée par l'application (singleton chargé
    via `ParametreDelai.actuel()`).
    """

    delai_compteur_shunte = models.PositiveIntegerField(
        "délai compteur shunté (heures)", default=48, validators=[MinValueValidator(1)]
    )
    delai_sans_electricite = models.PositiveIntegerField(
        "délai client sans électricité (heures)", default=24, validators=[MinValueValidator(1)]
    )
    delai_autre_equipement = models.PositiveIntegerField(
        "délai autres équipements (heures)", default=48, validators=[MinValueValidator(1)]
    )
    seuil_alerte_pct = models.PositiveIntegerField(
        "seuil d'alerte anticipée (%)",
        default=75,
        validators=[MinValueValidator(10), MaxValueValidator(100)],
    )
    appliquer_dossiers_ouverts = models.BooleanField(
        "appliquer aux dossiers déjà ouverts", default=False
    )
    modifie_le = models.DateTimeField(auto_now=True)
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parametres_delai_modifies",
    )

    class Meta:
        verbose_name = "paramètre de délai"
        verbose_name_plural = "paramètres de délai"

    def __str__(self):
        return (
            f"Shunté {self.delai_compteur_shunte}h / "
            f"Sans élec. {self.delai_sans_electricite}h / "
            f"Autre {self.delai_autre_equipement}h"
        )

    @classmethod
    def actuel(cls):
        obj = cls.objects.order_by("pk").first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class HistoriqueDelai(models.Model):
    """Trace de chaque modification de délai : qui, quand, avant, après."""

    champ = models.CharField("champ", max_length=60)
    ancienne_valeur = models.CharField("ancienne valeur", max_length=40)
    nouvelle_valeur = models.CharField("nouvelle valeur", max_length=40)
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    modifie_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "historique de délai"
        verbose_name_plural = "historique des délais"
        ordering = ["-modifie_le"]

    def __str__(self):
        return f"{self.champ}: {self.ancienne_valeur} -> {self.nouvelle_valeur}"


class NiveauZone(models.TextChoices):
    COMMUNE = "COMMUNE", "Commune"
    QUARTIER = "QUARTIER", "Quartier"
    SOUS_QUARTIER = "SOUS_QUARTIER", "Sous-quartier"


class Quartier(models.Model):
    """Découpage territorial importé depuis OpenStreetMap.

    Le contour est stocké en GeoJSON (WGS84, coordonnées [lon, lat]) : pas de
    dépendance à PostGIS, le rattachement point-dans-polygone se fait en Python
    avec un préfiltre par boîte englobante.
    """

    nom = models.CharField("nom", max_length=150)
    niveau = models.CharField(
        "niveau", max_length=13, choices=NiveauZone.choices, default=NiveauZone.QUARTIER
    )
    commune = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quartiers",
        verbose_name="commune de rattachement",
        limit_choices_to={"niveau": NiveauZone.COMMUNE},
    )
    # Renseigne seulement pour un SOUS_QUARTIER : le quartier qui le contient.
    # `commune` reste renseigné en parallèle (raccourci vers l'ancêtre commune,
    # évite de remonter la chaîne à chaque affichage).
    quartier = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sous_quartiers",
        verbose_name="quartier de rattachement",
        limit_choices_to={"niveau": NiveauZone.QUARTIER},
    )
    osm_id = models.BigIntegerField("identifiant OSM", null=True, blank=True, db_index=True)
    source = models.CharField("source du découpage", max_length=80, blank=True)

    # Géométrie GeoJSON : {"type": "Polygon"|"MultiPolygon", "coordinates": [...]}
    contour = models.JSONField("contour GeoJSON")

    # Boîte englobante : préfiltre rapide avant le test point-dans-polygone.
    lat_min = models.FloatField(db_index=True)
    lat_max = models.FloatField(db_index=True)
    lon_min = models.FloatField(db_index=True)
    lon_max = models.FloatField(db_index=True)
    centre_lat = models.FloatField()
    centre_lon = models.FloatField()

    actif = models.BooleanField("actif", default=True)
    importe_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "quartier"
        verbose_name_plural = "quartiers et communes"
        ordering = ["niveau", "nom"]
        indexes = [models.Index(fields=["niveau", "actif"])]

    def __str__(self):
        if self.niveau == NiveauZone.SOUS_QUARTIER and self.quartier_id:
            return f"{self.nom} ({self.quartier.nom})"
        if self.niveau == NiveauZone.QUARTIER and self.commune_id:
            return f"{self.nom} ({self.commune.nom})"
        return self.nom

    # --- Géométrie -------------------------------------------------------

    @property
    def polygones(self):
        """Liste de polygones, chacun étant [anneau_exterieur, trous...]."""
        geometrie = self.contour or {}
        if geometrie.get("type") == "Polygon":
            return [geometrie.get("coordinates", [])]
        if geometrie.get("type") == "MultiPolygon":
            return geometrie.get("coordinates", [])
        return []

    def contient(self, lat, lon):
        """Test point-dans-polygone (lancer de rayon), trous compris."""
        if lat is None or lon is None:
            return False
        if not (self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max):
            return False
        for polygone in self.polygones:
            if not polygone:
                continue
            if _dans_anneau(lon, lat, polygone[0]):
                # Le point est hors du quartier s'il tombe dans un trou.
                if not any(_dans_anneau(lon, lat, trou) for trou in polygone[1:]):
                    return True
        return False

    @property
    def surface_approx_km2(self):
        """Surface approchée, suffisante pour classer du plus fin au plus large."""
        degre_lat_km = 111.32
        degre_lon_km = degre_lat_km * math.cos(math.radians(self.centre_lat))
        return (
            (self.lat_max - self.lat_min) * degre_lat_km
            * (self.lon_max - self.lon_min) * degre_lon_km
        )

    # --- Rattachement ----------------------------------------------------

    @classmethod
    def localiser(cls, lat, lon, niveau=None):
        """Zone contenant ce point, la plus fine en cas de superposition."""
        if lat is None or lon is None:
            return None
        candidats = cls.objects.filter(
            actif=True,
            lat_min__lte=lat,
            lat_max__gte=lat,
            lon_min__lte=lon,
            lon_max__gte=lon,
        )
        if niveau:
            candidats = candidats.filter(niveau=niveau)
        trouves = [zone for zone in candidats if zone.contient(lat, lon)]
        if not trouves:
            return None
        return min(trouves, key=lambda z: z.surface_approx_km2)

    @classmethod
    def localiser_complet(cls, lat, lon):
        """Renvoie (sous_quartier, quartier, commune) pour une position donnée.

        Chaque niveau remonte à l'ancêtre connu du niveau supérieur quand il
        est renseigné, pour éviter un test point-dans-polygone redondant.
        """
        sous_quartier = cls.localiser(lat, lon, niveau=NiveauZone.SOUS_QUARTIER)

        quartier = sous_quartier.quartier if sous_quartier and sous_quartier.quartier_id else None
        if quartier is None:
            quartier = cls.localiser(lat, lon, niveau=NiveauZone.QUARTIER)

        commune = None
        if sous_quartier is not None and sous_quartier.commune_id:
            commune = sous_quartier.commune
        elif quartier is not None and quartier.commune_id:
            commune = quartier.commune
        if commune is None:
            commune = cls.localiser(lat, lon, niveau=NiveauZone.COMMUNE)

        return sous_quartier, quartier, commune


class AffectationAgent(models.Model):
    """Périmètre géographique d'un agent dans cette application.

    `core.Agent` (identité partagée avec django_dran) ne porte aucun champ
    `structure`/`secteurs` — c'est un référentiel propre à dépannage, tenu
    ici. Le rôle (Dépanneur, Responsable, ...) vit séparément dans
    `core.AccesApplication` (voir `depannages.profils`) : cette table ne gère
    que le PÉRIMÈTRE (quelle structure, quels secteurs), pas les droits.
    """

    agent = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="affectation_depannage",
        verbose_name="agent",
    )
    structure = models.ForeignKey(
        Structure,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="agents_affectes",
        verbose_name="structure de rattachement",
    )
    secteurs = models.ManyToManyField(
        Secteur,
        blank=True,
        related_name="agents_affectes",
        verbose_name="secteurs visibles",
        help_text="Laisser vide pour donner accès à tous les secteurs de la structure.",
    )
    telephone = models.CharField("téléphone", max_length=30, blank=True)

    class Meta:
        verbose_name = "affectation d'agent"
        verbose_name_plural = "affectations d'agents"

    def __str__(self):
        return f"{self.agent} — {self.structure or 'aucune structure'}"


def _dans_anneau(lon, lat, anneau):
    """Lancer de rayon horizontal sur un anneau fermé de coordonnées [lon, lat]."""
    dedans = False
    nombre = len(anneau)
    if nombre < 3:
        return False
    j = nombre - 1
    for i in range(nombre):
        xi, yi = anneau[i][0], anneau[i][1]
        xj, yj = anneau[j][0], anneau[j][1]
        if (yi > lat) != (yj > lat):
            if lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                dedans = not dedans
        j = i
    return dedans
