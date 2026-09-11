"""
Routeur de base pour un déploiement **multi-projets sur une base partagée**.

Contexte cible : les applications ne vivront pas dans le même dossier, mais
partageront la même base PostgreSQL. Deux projets Django qui appliquent leurs
migrations sur la même base finissent toujours par se contredire : l'un crée
une table que l'autre croit devoir créer, l'un supprime un type de contenu que
l'autre utilise.

Règle retenue, la plus simple à exploiter :

    Un seul projet est **propriétaire du socle** (`DR_SOCLE_PROPRIETAIRE=1`).
    Il applique les migrations de `core`, `auth`, `contenttypes`, `sessions`
    et `admin`. Les autres projets installent le socle pour lire les agents,
    les directions et les droits, mais ne migrent que leurs propres tables.

Activation dans `settings.py` :

    DATABASE_ROUTERS = ["core.routers.RouteurBasePartagee"]
    DR_SOCLE_PROPRIETAIRE = env_bool("DR_SOCLE_PROPRIETAIRE", True)
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger("dran")

# Applications dont les tables appartiennent au socle.
APPLICATIONS_SOCLE = {"core", "auth", "contenttypes", "sessions", "admin"}


class RouteurBasePartagee:
    """Empêche un projet non propriétaire de migrer les tables du socle."""

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label not in APPLICATIONS_SOCLE:
            return None  # décision laissée à Django pour les tables métier

        if getattr(settings, "DR_SOCLE_PROPRIETAIRE", True):
            return None

        # Projet satellite : il lit le socle mais ne le fait pas évoluer.
        return False

    def db_for_read(self, model, **hints):
        return None

    def db_for_write(self, model, **hints):
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Toutes les données vivent dans la même base : les relations
        # socle <-> métier sont légitimes.
        return True
