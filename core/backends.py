"""Backend d'authentification par matricule."""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

logger = logging.getLogger("dran.security")


class MatriculeBackend(ModelBackend):
    """
    Authentifie un agent par son matricule.

    Deux différences avec l'implémentation Flask :
      * le matricule est nettoyé (espaces insécables collés/copiés depuis Excel) ;
      * un hachage factice est calculé quand l'agent n'existe pas, pour que le
        temps de réponse ne révèle pas l'existence du compte (timing oracle).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        matricule = username or kwargs.get(UserModel.USERNAME_FIELD)
        matricule = (matricule or "").replace("\xa0", "").strip()
        if not matricule or password is None:
            UserModel().set_password(password or "")
            return None

        try:
            agent = UserModel._default_manager.get(matricule__iexact=matricule)
        except UserModel.DoesNotExist:
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:  # pragma: no cover - données incohérentes
            logger.error("Plusieurs agents pour le matricule %s", matricule)
            return None

        if not agent.check_password(password):
            return None
        if not self.user_can_authenticate(agent):
            logger.info("Connexion refusée : compte désactivé (%s)", matricule)
            return None
        return agent
