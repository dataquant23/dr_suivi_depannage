from django.urls import path

from . import views

app_name = "comptes"

urlpatterns = [
    path("connexion/", views.connexion, name="connexion"),
    path("deconnexion/", views.deconnexion, name="deconnexion"),
    path("profil/", views.profil, name="profil"),
    path("acces/", views.gestion_acces, name="gestion_acces"),
    # Mot de passe : changement (imposé ou volontaire) et réinitialisation
    path(
        "mot-de-passe/changer/",
        views.changer_mot_de_passe,
        name="changer_mot_de_passe",
    ),
    path(
        "mot-de-passe/oublie/",
        views.mot_de_passe_oublie,
        name="mot_de_passe_oublie",
    ),
    path(
        "mot-de-passe/reinitialiser/<uidb64>/<token>/",
        views.mot_de_passe_reinitialiser,
        name="mot_de_passe_reinitialiser",
    ),
    # WebAuthn : enrolement de l'empreinte sur l'appareil
    path("webauthn/enroler/debut/", views.webauthn_enrolement_debut, name="webauthn_enrolement_debut"),
    path("webauthn/enroler/fin/", views.webauthn_enrolement_fin, name="webauthn_enrolement_fin"),
    path("webauthn/cle/<int:pk>/supprimer/", views.webauthn_supprimer, name="webauthn_supprimer"),
    # WebAuthn : connexion par empreinte
    path("webauthn/connexion/debut/", views.webauthn_connexion_debut, name="webauthn_connexion_debut"),
    path("webauthn/connexion/fin/", views.webauthn_connexion_fin, name="webauthn_connexion_fin"),
]
