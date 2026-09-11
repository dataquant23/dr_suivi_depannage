from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Socle commun (agents, secteurs, agences)"

    def ready(self):
        # Contrôles de cohérence de l'authentification unique et de la base partagée.
        from core import checks  # noqa: F401
