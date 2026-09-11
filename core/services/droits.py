"""
Synchronisation des profils (groupes Django) et de leurs permissions.

Appelée automatiquement après chaque `migrate` et par la commande
`manage.py initialiser_profils`. L'opération est idempotente : elle aligne les
groupes sur la matrice déclarée dans `core.profils`.
"""
from __future__ import annotations

import logging

from django.contrib.auth.models import Group, Permission

from core.profils import APPLICATIONS, PROFILS, profil_pour_fonction

logger = logging.getLogger("dran")


def enregistre_applications() -> int:
    """
    Alimente le registre `core.ApplicationMetier` depuis `core.profils.APPLICATIONS`.

    Le registre reste vrai même si l'application correspondante n'est pas
    installée dans le projet courant : c'est ce qui permet à plusieurs projets
    de partager la même base sans se marcher dessus.
    """
    from core.models import ApplicationMetier

    for code, definition in APPLICATIONS.items():
        ApplicationMetier.objects.update_or_create(
            code=code,
            defaults={"nom": definition["nom"], "description": definition.get("description", "")},
        )
    return len(APPLICATIONS)


def permission_depuis_chemin(chemin: str) -> Permission | None:
    """« recouvrement.acces_recouvrement » -> instance `Permission`."""
    app_label, codename = chemin.split(".", 1)
    return Permission.objects.filter(
        content_type__app_label=app_label, codename=codename
    ).first()


def synchronise_profils(verbeux: bool = False) -> dict[str, int]:
    """Crée/actualise un groupe par profil et y attache ses permissions."""
    enregistre_applications()
    resume: dict[str, int] = {}
    for nom_profil, definition in PROFILS.items():
        groupe, _ = Group.objects.get_or_create(name=nom_profil)
        permissions, manquantes = [], []
        for chemin in definition["permissions"]:
            permission = permission_depuis_chemin(chemin)
            if permission is None:
                manquantes.append(chemin)
            else:
                permissions.append(permission)
        groupe.permissions.set(permissions)
        resume[nom_profil] = len(permissions)
        if manquantes:
            logger.warning("Permissions introuvables pour le profil %s : %s", nom_profil, manquantes)
        if verbeux:
            logger.info("Profil %s : %s permission(s)", nom_profil, len(permissions))
    return resume


def affecte_profils_automatiquement(agents=None) -> dict[str, int]:
    """
    Rattache chaque agent au profil déduit de sa fonction RH.

    Les agents déjà rattachés à un groupe ne sont pas modifiés : les décisions
    prises manuellement en administration priment.
    """
    from django.contrib.auth import get_user_model

    Agent = get_user_model()
    agents = agents if agents is not None else Agent.objects.all()
    compteur: dict[str, int] = {}

    for agent in agents:
        if agent.groups.exists():
            continue
        profil = profil_pour_fonction(agent.fonction)
        agent.affecter_profil(profil)
        compteur[profil] = compteur.get(profil, 0) + 1
    return compteur
