from django.contrib import admin

from .models import Depannage, HistoriqueStatut, PhotoDepannage


class PhotoInline(admin.TabularInline):
    model = PhotoDepannage
    extra = 0


class HistoriqueInline(admin.TabularInline):
    model = HistoriqueStatut
    extra = 0
    readonly_fields = ("statut_avant", "statut_apres", "action", "utilisateur", "horodatage")


@admin.register(Depannage)
class DepannageAdmin(admin.ModelAdmin):
    list_display = (
        "numero_bt",
        "secteur",
        "type_intervention",
        "categorie_provisoire",
        "statut",
        "date_saisie",
        "cree_par",
    )
    list_filter = ("type_intervention", "categorie_provisoire", "statut", "secteur", "structure")
    search_fields = ("numero_bt", "adresse_saisie", "commentaire")
    filter_horizontal = ("equipements",)
    date_hierarchy = "date_saisie"
    inlines = [PhotoInline, HistoriqueInline]
