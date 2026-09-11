from __future__ import annotations

from django.contrib.auth.models import BaseUserManager


class AgentManager(BaseUserManager):
    """Gestionnaire d'agents : l'identifiant de connexion est le matricule."""

    use_in_migrations = True

    def _create_user(self, matricule: str, password: str | None, **extra):
        matricule = (matricule or "").replace("\xa0", "").strip()
        if not matricule:
            raise ValueError("Le matricule est obligatoire.")
        email = extra.pop("email", "") or ""
        agent = self.model(matricule=matricule, email=self.normalize_email(email).lower(), **extra)
        agent.set_password(password)
        agent.full_clean(exclude=["password", "last_login"])
        agent.save(using=self._db)
        return agent

    def create_user(self, matricule: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(matricule, password, **extra)

    def create_superuser(self, matricule: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("must_change_password", False)
        extra.setdefault("nom", "Administrateur")
        extra.setdefault("prenoms", "DRAN")
        extra.setdefault("fonction", "Administrateur systeme")
        extra.setdefault("site", "DRAN")
        if extra["is_staff"] is not True:
            raise ValueError("Un superutilisateur doit avoir is_staff=True.")
        if extra["is_superuser"] is not True:
            raise ValueError("Un superutilisateur doit avoir is_superuser=True.")
        return self._create_user(matricule, password, **extra)

    def actifs(self):
        return self.get_queryset().filter(is_active=True)
