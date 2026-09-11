from django.urls import path

from . import views, vues_zones

app_name = "depannages"

urlpatterns = [
    path("", views.tableau_bord, name="tableau_bord"),
    path("saisie/", views.saisie, name="saisie"),
    path("dossier/<int:pk>/", views.detail, name="detail"),
    path("dossier/<int:pk>/cloturer/", views.cloturer, name="cloturer"),
    path("cloture/", views.recherche_cloture, name="recherche_cloture"),
    path("dossier/<int:pk>/itineraire/", views.itineraire, name="itineraire"),
    path("travaux-en-cours/", views.travaux_en_cours, name="travaux_en_cours"),
    path("dossiers-clotures/", views.dossiers_clotures, name="dossiers_clotures"),
    path("carte/", views.carte, name="carte"),
    path("carte/donnees/", views.carte_donnees, name="carte_donnees"),
    path("zones/", vues_zones.zones, name="zones"),
    path("zones/geojson/", vues_zones.zones_geojson, name="zones_geojson"),
    path("recapitulatif/", views.recapitulatif, name="recapitulatif"),
    path("alertes/", views.alertes, name="alertes"),
    path("recherche/", views.recherche, name="recherche"),
]
