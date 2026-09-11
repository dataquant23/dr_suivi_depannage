"""Envoi des emails transactionnels (via la couche mail de Django)."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger("dran")

SUJET_RESET = "Réinitialisation de votre mot de passe DRAN"


def envoie_lien_reinitialisation(destinataire: str, lien: str) -> None:
    """
    Envoie le lien de réinitialisation.

    Les identifiants SMTP viennent des variables d'environnement : ils ne sont
    plus écrits dans le code comme dans l'application Flask.
    """
    duree_minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    corps = (
        "Bonjour,\n\n"
        "Vous avez demandé la réinitialisation de votre mot de passe.\n"
        f"Ce lien est valable {duree_minutes} minutes :\n{lien}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"
    )
    message = EmailMessage(
        subject=SUJET_RESET,
        body=corps,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinataire],
    )
    message.send(fail_silently=False)
    logger.info("Lien de réinitialisation envoyé à %s", destinataire)


SUJET_ACTIVATION = "Activation de votre compte DRAN"


def envoie_identifiants_activation(destinataire: str, matricule: str, mot_de_passe: str) -> None:
    """
    Envoie un mot de passe temporaire pour la première connexion.

    À la différence du lien de réinitialisation, ce mot de passe est généré
    côté serveur et transite en clair par email : c'est un choix assumé pour
    simplifier l'activation (moins d'étapes qu'un lien), au prix d'un risque
    résiduel si la boîte mail est compromise après coup. Le mot de passe est
    à usage unique — `must_change_password` force son remplacement dès la
    première connexion.
    """
    corps = (
        "Bonjour,\n\n"
        "Un mot de passe temporaire vient d'être généré pour activer votre compte DRAN.\n\n"
        f"Matricule : {matricule}\n"
        f"Mot de passe temporaire : {mot_de_passe}\n\n"
        "Connectez-vous avec ces identifiants : un nouveau mot de passe personnel "
        "vous sera demandé dès la première connexion.\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : "
        "votre compte reste inchangé tant que personne ne se connecte avec ce "
        "mot de passe.\n"
    )
    message = EmailMessage(
        subject=SUJET_ACTIVATION,
        body=corps,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinataire],
    )
    message.send(fail_silently=False)
    logger.info("Identifiants d'activation envoyés à %s", destinataire)
