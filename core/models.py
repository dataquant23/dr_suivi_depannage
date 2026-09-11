"""Modèles partagés par les deux applications métier."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from core.managers import AgentManager
from core.utils.text import secteur_key

CODE_SECTEUR_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-z0-9]{1,3}$",
    message="Le code secteur doit contenir de 1 à 3 caractères alphanumériques.",
)

CODE_DIRECTION_VALIDATOR = RegexValidator(
    regex=r"^[A-Z0-9]{2,10}$",
    message="Le code direction doit contenir de 2 à 10 caractères majuscules ou chiffres.",
)


class TimeStampedModel(models.Model):
    """Horodatage systématique : utile pour l'audit et le support."""

    cree_le = models.DateTimeField("créé le", default=timezone.now, editable=False)
    modifie_le = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        abstract = True


class DirectionRegionale(models.Model):
    """
    Direction régionale exploitant l'application.

    Le projet est prévu pour héberger plusieurs directions sur la même base :
    tous les référentiels et toutes les données transactionnelles portent une
    référence vers leur direction, et les agents ne voient que la leur.
    """

    code = models.CharField(
        "code",
        max_length=10,
        unique=True,
        db_index=True,
        validators=[CODE_DIRECTION_VALIDATOR],
        help_text="Ex. : DRAN, DRAS, DRCE. Sert de préfixe aux tickets et de dossier de stockage.",
    )
    code_secteur = models.CharField(
        "code (espace secteurs)",
        max_length=3,
        default="000",
        validators=[CODE_SECTEUR_VALIDATOR],
        help_text="Identifiant numérique de la direction elle-même, dans le même espace que "
        "ses secteurs (ex. DRAN=040, secteurs 041 à 049).",
    )
    nom = models.CharField(max_length=150)
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = "direction régionale"
        verbose_name_plural = "directions régionales"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.nom}"

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        self.code_secteur = (self.code_secteur or "").strip().upper()
        super().save(*args, **kwargs)

    @classmethod
    def par_defaut(cls) -> "DirectionRegionale":
        """Direction utilisée quand le contexte n'en impose pas (installation mono-DR)."""
        direction, _ = cls.objects.get_or_create(
            code=settings.DR_CODE_DEFAUT, defaults={"nom": settings.DR_NOM_DEFAUT}
        )
        return direction


class ApplicationMetier(models.Model):
    """
    Registre des applications du système d'information DRAN.

    Ce modèle appartient au **socle** et porte **toutes** les permissions
    applicatives, y compris celles des applications qui ne sont pas installées
    dans le projet courant.

    Pourquoi : les applications ne vivront pas toutes dans le même projet, mais
    partageront la même base. Si chaque application accrochait ses permissions
    à ses propres modèles :
      * un projet qui n'installe pas `recouvrement` ne verrait plus ses
        permissions, et `has_perm("recouvrement.…")` deviendrait indécidable ;
      * `manage.py remove_stale_contenttypes` lancé depuis ce projet
        supprimerait les types de contenu « inconnus » — donc les permissions
        des autres applications, donc les droits de tous les agents.

    En centralisant ici, il suffit d'installer le socle pour que les droits
    soient lisibles et vérifiables depuis n'importe quelle application.
    """

    code = models.CharField(max_length=50, unique=True, db_index=True)
    nom = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    url_base = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Adresse publique de l'application, ex. https://visite.dran.ci/",
    )
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "application métier"
        verbose_name_plural = "applications métier"
        ordering = ["code"]
        permissions = [
            # --- Socle uniquement. Les droits applicatifs par application
            # (import, export, validation, saisie...) ne sont plus portés par
            # des permissions Django : chaque application définit son propre
            # catalogue de profils/droits (`<app>.profils.PROFILS`) et
            # l'accès d'un agent est enregistré dans `core.AccesApplication`.
            # Voir le plan « Accès et profils par application ».
            ("gerer_utilisateurs", "Socle : gérer les utilisateurs et leurs droits"),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.nom}"

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().lower()
        super().save(*args, **kwargs)


class ObjetDirection(models.Model):
    """Base des modèles rattachés à une direction régionale."""

    direction = models.ForeignKey(
        DirectionRegionale,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)ss",
        verbose_name="direction régionale",
    )

    class Meta:
        abstract = True


class Secteur(ObjetDirection):
    """Secteur de recouvrement, identifié par les 3 premiers chiffres du contrat."""

    nom = models.CharField(max_length=120)
    code_secteur = models.CharField(
        max_length=3, db_index=True, default="000", validators=[CODE_SECTEUR_VALIDATOR]
    )

    class Meta:
        verbose_name = "secteur"
        verbose_name_plural = "secteurs"
        ordering = ["direction", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["direction", "nom"], name="uniq_secteur_nom_par_direction"),
            models.UniqueConstraint(
                fields=["direction", "code_secteur"], name="uniq_secteur_code_par_direction"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.nom} ({self.code_secteur})"

    def save(self, *args, **kwargs):
        self.nom = secteur_key(self.nom)
        self.code_secteur = (self.code_secteur or "").strip().upper()
        super().save(*args, **kwargs)

    @classmethod
    def noms(cls, direction=None) -> list[str]:
        requete = cls.objects.all()
        if direction is not None:
            requete = requete.filter(direction=direction)
        return list(requete.order_by("code_secteur").values_list("nom", flat=True))

    @classmethod
    def map_code_vers_nom(cls, direction=None) -> dict[str, str]:
        requete = cls.objects.all()
        if direction is not None:
            requete = requete.filter(direction=direction)
        return {
            (code or "").strip(): (nom or "").strip()
            for code, nom in requete.values_list("code_secteur", "nom")
            if code and nom
        }


class Agence(ObjetDirection):
    """Agence commerciale (portail visite client)."""

    nom = models.CharField(max_length=120)
    code_secteur = models.CharField(
        max_length=3, default="000", validators=[CODE_SECTEUR_VALIDATOR], db_index=True
    )

    class Meta:
        verbose_name = "agence"
        verbose_name_plural = "agences"
        ordering = ["direction", "code_secteur", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["direction", "nom"], name="uniq_agence_nom_par_direction")
        ]

    def __str__(self) -> str:
        return self.nom


class Agent(AbstractBaseUser, PermissionsMixin):
    """
    Agent DRAN — c'est aussi l'utilisateur Django (`AUTH_USER_MODEL`).

    Les droits ne dépendent plus d'un test sur l'intitulé du poste : ils sont
    portés par le profil (groupe Django) auquel l'agent est rattaché.
    Voir `core.profils`.
    """

    matricule = models.CharField(
        "matricule",
        max_length=30,
        unique=True,
        db_index=True,
        validators=[RegexValidator(r"^[A-Za-z0-9._-]{2,30}$", "Matricule invalide.")],
    )
    nom = models.CharField(max_length=80)
    prenoms = models.CharField(max_length=160)
    fonction = models.CharField(max_length=120, blank=True, default="")
    site = models.CharField(max_length=120, blank=True, default="")
    email = models.EmailField(max_length=255, blank=True, null=True, unique=True)

    direction = models.ForeignKey(
        DirectionRegionale,
        on_delete=models.PROTECT,
        related_name="agents",
        null=True,
        blank=True,
        verbose_name="direction régionale",
        help_text="Laisser vide pour un compte technique national (superutilisateur).",
    )

    must_change_password = models.BooleanField("doit changer son mot de passe", default=True)
    is_active = models.BooleanField("actif", default=True)
    is_staff = models.BooleanField("accès à l'administration", default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = AgentManager()

    USERNAME_FIELD = "matricule"
    REQUIRED_FIELDS = ["nom", "prenoms"]

    class Meta:
        verbose_name = "agent"
        verbose_name_plural = "agents"
        ordering = ["nom", "prenoms"]

    def __str__(self) -> str:
        return f"{self.matricule} — {self.display_name()}"

    def clean(self):
        super().clean()
        self.matricule = (self.matricule or "").replace("\xa0", "").strip()
        self.email = (self.email or "").strip().lower() or None

    @property
    def premier_prenom(self) -> str:
        prenoms = (self.prenoms or "").strip()
        return prenoms.split()[0] if prenoms else ""

    def display_name(self) -> str:
        return f"{(self.nom or '').strip()} {self.premier_prenom}".strip()

    def get_full_name(self) -> str:
        return self.display_name()

    def get_short_name(self) -> str:
        return self.premier_prenom or self.matricule

    # -- Profils et droits ------------------------------------------------
    @property
    def profils(self) -> list[str]:
        return list(self.groups.values_list("name", flat=True))

    @property
    def profil(self) -> str:
        """Profil principal (le premier groupe), à titre d'affichage."""
        return next(iter(self.profils), "")

    def affecter_profil(self, nom_profil: str) -> None:
        """Remplace les profils de l'agent par celui indiqué."""
        from django.contrib.auth.models import Group

        groupe, _ = Group.objects.get_or_create(name=nom_profil)
        self.groups.set([groupe])

    # -- Périmètre ---------------------------------------------------------
    @property
    def direction_effective(self) -> DirectionRegionale | None:
        """Direction de rattachement ; `None` pour un compte national."""
        return self.direction

    def voit_toutes_les_directions(self) -> bool:
        return self.is_superuser and self.direction_id is None


class AccesApplication(models.Model):
    """
    Accès d'un agent à une application, avec le profil qu'il y a.

    Remplace le mécanisme des permissions Django partagées entre toutes les
    applications : chaque application définit son propre catalogue de
    profils/droits dans son code (`<app>.profils.PROFILS`), et cette table
    enregistre juste, pour un couple (agent, application), si l'accès est
    actif et quel profil de ce catalogue s'applique. `profil` est donc une
    simple chaîne — sa signification (quels droits elle donne) n'existe que
    dans le catalogue Python de l'application concernée, jamais ici.

    Vit dans le socle (comme `ApplicationMetier`) pour être lisible et
    modifiable depuis n'importe quel projet partageant la base, y compris
    ceux qui n'installent pas l'application concernée.
    """

    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="acces_applications"
    )
    application = models.ForeignKey(ApplicationMetier, on_delete=models.CASCADE, related_name="acces")
    profil = models.CharField(max_length=100)
    actif = models.BooleanField(default=True)
    accorde_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acces_accordes",
    )
    accorde_le = models.DateTimeField(default=timezone.now)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "accès application"
        verbose_name_plural = "accès applications"
        ordering = ["application", "agent"]
        constraints = [
            models.UniqueConstraint(fields=["agent", "application"], name="uniq_acces_par_application")
        ]

    def __str__(self) -> str:
        statut = "actif" if self.actif else "inactif"
        return f"{self.agent.matricule} — {self.application.code} — {self.profil} ({statut})"
