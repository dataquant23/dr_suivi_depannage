from django.contrib import admin

from .models import (
    Equipement,
    HistoriqueDelai,
    ParametreDelai,
    Quartier,
    Secteur,
    Structure,
)


@admin.register(Structure)
class StructureAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "type_structure", "actif")
    list_filter = ("type_structure", "actif")
    search_fields = ("code", "libelle")


@admin.register(Secteur)
class SecteurAdmin(admin.ModelAdmin):
    list_display = ("libelle", "code", "structure", "actif")
    list_filter = ("structure", "actif")
    search_fields = ("code", "libelle")


@admin.register(Equipement)
class EquipementAdmin(admin.ModelAdmin):
    list_display = ("libelle", "structure", "categorie", "actif")
    list_filter = ("structure", "actif", "categorie")
    search_fields = ("libelle", "code")


@admin.register(ParametreDelai)
class ParametreDelaiAdmin(admin.ModelAdmin):
    list_display = (
        "delai_compteur_shunte",
        "delai_sans_electricite",
        "delai_autre_equipement",
        "seuil_alerte_pct",
        "modifie_le",
    )


@admin.register(HistoriqueDelai)
class HistoriqueDelaiAdmin(admin.ModelAdmin):
    list_display = ("champ", "ancienne_valeur", "nouvelle_valeur", "modifie_par", "modifie_le")
    list_filter = ("champ",)


@admin.register(Quartier)
class QuartierAdmin(admin.ModelAdmin):
    list_display = ("nom", "niveau", "commune", "source", "actif")
    list_filter = ("niveau", "actif", "commune")
    search_fields = ("nom", "osm_id")
    readonly_fields = ("lat_min", "lat_max", "lon_min", "lon_max", "centre_lat", "centre_lon")
