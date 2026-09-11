"""Rôle et périmètre de l'agent (core.AccesApplication + AffectationAgent).

Ces fonctions prennent l'agent en paramètre (le rôle n'est plus une
propriété du modèle utilisateur).
"""
from __future__ import annotations

from core.services.acces import a_le_droit

from .profils import PROFILS

CODE_APPLICATION = "depannages"


def peut_saisir(agent) -> bool:
    return a_le_droit(agent, CODE_APPLICATION, "saisir", PROFILS)


def est_responsable(agent) -> bool:
    return a_le_droit(agent, CODE_APPLICATION, "responsable", PROFILS)


def est_agent_dcrd(agent) -> bool:
    return a_le_droit(agent, CODE_APPLICATION, "dcrd", PROFILS)


def est_admin(agent) -> bool:
    return a_le_droit(agent, CODE_APPLICATION, "admin", PROFILS)


def secteurs_autorises(agent):
    """Secteurs que l'agent peut consulter.

    Un responsable/administrateur voit toute sa structure ; un agent limité à
    certains secteurs (via `referentiel.AffectationAgent.secteurs`) ne voit
    que les siens. Un agent sans affectation voit tous les secteurs actifs
    (comportement identique à l'ancien `Utilisateur.secteurs_autorises`
    lorsque `structure`/`secteurs` n'étaient pas renseignés).
    """
    from referentiel.models import Secteur

    base = Secteur.objects.filter(actif=True)
    if est_admin(agent):
        return base

    affectation = getattr(agent, "affectation_depannage", None)
    if affectation is not None and affectation.structure_id:
        base = base.filter(structure_id=affectation.structure_id)
    if not est_responsable(agent) and affectation is not None and affectation.secteurs.exists():
        base = base.filter(pk__in=affectation.secteurs.values("pk"))
    return base
