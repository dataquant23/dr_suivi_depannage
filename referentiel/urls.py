from django.urls import path

from . import views

app_name = "referentiel"

urlpatterns = [
    path("administration/", views.administration, name="administration"),
    path("delais/", views.parametres_delais, name="delais"),
    path("utilisateurs/", views.liste_utilisateurs, name="utilisateurs"),
    path("utilisateurs/nouveau/", views.creer_utilisateur, name="creer_utilisateur"),
    path("utilisateurs/<int:pk>/", views.modifier_utilisateur, name="modifier_utilisateur"),
    path("utilisateurs/<int:pk>/basculer/", views.basculer_utilisateur, name="basculer_utilisateur"),
    path("utilisateurs/<int:pk>/renvoyer-acces/", views.renvoyer_acces, name="renvoyer_acces"),
]
