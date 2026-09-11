"""
Administration Django du socle.

Elle remplace l'ancienne page `/admin/tables` de l'application Flask, qui
n'était protégée par aucun contrôle d'accès (le décorateur `admin_required`
était commenté) et exposait donc en clair l'ensemble des tables.
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.utils.translation import gettext_lazy as _

from core.models import AccesApplication, Agence, Agent, ApplicationMetier, DirectionRegionale, Secteur


@admin.register(Agent)
class AgentAdmin(UserAdmin):
    change_password_form = AdminPasswordChangeForm
    ordering = ("nom", "prenoms")
    list_display = (
        "matricule",
        "nom",
        "prenoms",
        "fonction",
        "profil_affiche",
        "direction",
        "site",
        "is_active",
    )
    list_filter = ("direction", "groups", "is_active", "is_staff", "must_change_password", "site")
    list_select_related = ("direction",)
    search_fields = ("matricule", "nom", "prenoms", "email", "site")
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("matricule", "password")}),
        (_("Identité"), {"fields": ("nom", "prenoms", "email")}),
        (_("Affectation"), {"fields": ("direction", "fonction", "site")}),
        (
            _("Droits"),
            {
                "fields": (
                    "is_active",
                    "must_change_password",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "matricule",
                    "nom",
                    "prenoms",
                    "direction",
                    "fonction",
                    "site",
                    "email",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    actions = ["desactiver", "forcer_changement_mot_de_passe", "reappliquer_profil"]

    @admin.display(description="profil")
    def profil_affiche(self, obj) -> str:
        return obj.profil or "—"

    @admin.action(description="Désactiver les agents sélectionnés")
    def desactiver(self, request, queryset):
        nombre = queryset.update(is_active=False)
        self.message_user(request, f"{nombre} agent(s) désactivé(s).")

    @admin.action(description="Forcer le changement de mot de passe")
    def forcer_changement_mot_de_passe(self, request, queryset):
        nombre = queryset.update(must_change_password=True)
        self.message_user(request, f"{nombre} agent(s) devront changer leur mot de passe.")

    @admin.action(description="Réappliquer le profil déduit de la fonction")
    def reappliquer_profil(self, request, queryset):
        from core.profils import profil_pour_fonction

        for agent in queryset:
            agent.affecter_profil(profil_pour_fonction(agent.fonction))
        self.message_user(request, f"{queryset.count()} agent(s) rattaché(s) à leur profil.")


@admin.register(ApplicationMetier)
class ApplicationMetierAdmin(admin.ModelAdmin):
    """
    Registre des applications du SI.

    Ce modèle porte les permissions applicatives de **toutes** les
    applications, y compris celles déployées dans un autre projet.
    """

    list_display = ("code", "nom", "active", "url_base", "nb_acces_actifs")
    list_filter = ("active",)
    search_fields = ("code", "nom", "description")

    @admin.display(description="agents avec accès actif")
    def nb_acces_actifs(self, obj) -> int:
        return obj.acces.filter(actif=True).count()


@admin.register(AccesApplication)
class AccesApplicationAdmin(admin.ModelAdmin):
    list_display = ("agent", "application", "profil", "actif", "accorde_par", "accorde_le")
    list_filter = ("application", "profil", "actif")
    search_fields = ("agent__matricule", "agent__nom", "agent__prenoms", "profil")
    list_select_related = ("agent", "application", "accorde_par")
    autocomplete_fields = ("agent", "accorde_par")


@admin.register(DirectionRegionale)
class DirectionRegionaleAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "actif", "nb_secteurs", "nb_agents")
    list_filter = ("actif",)
    search_fields = ("code", "nom")

    @admin.display(description="secteurs")
    def nb_secteurs(self, obj) -> int:
        return obj.core_secteurs.count()

    @admin.display(description="agents")
    def nb_agents(self, obj) -> int:
        return obj.agents.count()


@admin.register(Secteur)
class SecteurAdmin(admin.ModelAdmin):
    list_display = ("nom", "code_secteur", "direction")
    list_filter = ("direction",)
    search_fields = ("nom", "code_secteur")
    ordering = ("direction", "nom")
    list_select_related = ("direction",)


@admin.register(Agence)
class AgenceAdmin(admin.ModelAdmin):
    list_display = ("nom", "code_secteur", "direction")
    list_filter = ("direction",)
    search_fields = ("nom", "code_secteur")
    ordering = ("direction", "code_secteur", "nom")
    list_select_related = ("direction",)
