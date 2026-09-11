"""
Accès et profils par application.

Chaque application définit son propre catalogue de profils dans son code
(`<app>.profils.PROFILS`, un dict `{nom_profil: {"description": ..., "droits": [...]}}`).
Ce module ne connaît aucun catalogue : il se contente de lire/écrire
`core.AccesApplication` (qui profil, actif ou non) et de vérifier un droit
contre le catalogue qu'on lui passe — c'est l'application appelante qui sait
quels droits existent chez elle.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render
from django.utils import timezone

logger = logging.getLogger("dran.security")


def acces_pour(agent, code_application: str):
    """Accès actif de `agent` à l'application `code_application`, ou `None`."""
    from core.models import AccesApplication

    if not getattr(agent, "is_authenticated", False):
        return None
    return (
        AccesApplication.objects.filter(
            agent=agent, application__code=code_application, actif=True
        )
        .select_related("application")
        .first()
    )


def profil_de(agent, code_application: str) -> str:
    """Nom du profil actif de `agent` dans `code_application`, chaîne vide si aucun."""
    acces = acces_pour(agent, code_application)
    return acces.profil if acces else ""


def a_le_droit(agent, code_application: str, droit: str, catalogue_profils: dict) -> bool:
    """
    `droit` fait-il partie des droits du profil actif de `agent` dans
    `code_application`, d'après `catalogue_profils` (le `PROFILS` local de
    cette application) ?

    Un superutilisateur (compte technique national) passe toujours, comme
    avec le système de permissions Django qu'il remplace.
    """
    if getattr(agent, "is_superuser", False):
        return True
    profil = profil_de(agent, code_application)
    if not profil:
        return False
    return droit in catalogue_profils.get(profil, {}).get("droits", [])


def definir_acces(agent, code_application: str, profil: str, actif: bool, accorde_par=None):
    """Crée ou met à jour l'accès de `agent` à `code_application`."""
    from core.models import AccesApplication, ApplicationMetier

    application = ApplicationMetier.objects.get(code=code_application)
    acces, _ = AccesApplication.objects.update_or_create(
        agent=agent,
        application=application,
        defaults={
            "profil": profil,
            "actif": actif,
            "accorde_par": accorde_par,
            "accorde_le": timezone.now(),
        },
    )
    return acces


ROLES_ENCADREMENT = {"Direction régionale", "Responsable commercial"}
ROLES_TERRAIN = {"Litige et recouvrement", "Conseiller clientèle", "Caisse"}


def initialise_acces_defaut(agent, accorde_par=None) -> None:
    """
    Accès applicatifs par défaut d'un agent, déduits de son rôle
    organisationnel (`agent.profil`) — reproduit la logique du backfill
    historique (migration `core.000X_backfill_acces_application`), réutilisée
    à la création d'un agent (`tests.factories.cree_agent`,
    `core.forms.AjouterUtilisateurForm`).

    N'écrase jamais un accès déjà défini explicitement (`get_or_create`, pas
    `update_or_create`) : ne s'applique qu'à un agent qui n'a encore aucun
    accès nulle part.
    """
    from core.models import AccesApplication, ApplicationMetier

    if AccesApplication.objects.filter(agent=agent).exists():
        return

    profil_org = agent.profil
    codes_actifs = set(ApplicationMetier.objects.values_list("code", flat=True))

    if profil_org in ROLES_ENCADREMENT:
        if "recouvrement" in codes_actifs:
            definir_acces(agent, "recouvrement", "Gestion", True, accorde_par)
        if "visite_client" in codes_actifs:
            definir_acces(agent, "visite_client", "Supervision", True, accorde_par)
        if "coupure" in codes_actifs:
            definir_acces(agent, "coupure", "Gestion", True, accorde_par)
    elif profil_org in ROLES_TERRAIN:
        if "visite_client" in codes_actifs:
            definir_acces(agent, "visite_client", "Saisie", True, accorde_par)


def acces_de_la_direction(direction, code_application: str):
    """
    Pour chaque agent de `direction`, son accès (ou `None`) à `code_application`.

    Retourne une liste de tuples `(agent, acces_ou_None)`, triée comme
    `Agent.objects` par défaut (nom, prénoms) — c'est ce qu'affiche l'écran
    « Gestion des accès » de chaque application.
    """
    from django.contrib.auth import get_user_model

    from core.models import AccesApplication

    Agent = get_user_model()
    agents = Agent.objects.filter(direction=direction) if direction is not None else Agent.objects.all()
    acces_par_agent = {
        acces.agent_id: acces
        for acces in AccesApplication.objects.filter(
            application__code=code_application, agent__in=agents
        ).select_related("application")
    }
    return [(agent, acces_par_agent.get(agent.pk)) for agent in agents]


def traite_gestion_acces(request, code_application: str, catalogue_profils: dict, template_name: str):
    """
    Écran « Gestion des accès » d'une application : liste les agents de la
    direction de l'agent connecté avec leur accès actuel, permet de
    l'activer/désactiver et de choisir un profil du catalogue local.

    Vue générique réutilisée par chaque application (comme
    `core.services.authentification.traite_connexion` pour la connexion) :
    l'application appelante ne fournit que son code, son catalogue de
    profils et son gabarit.
    """
    from core.tenants import direction_courante

    direction = direction_courante(request)

    if request.method == "POST":
        Agent = get_user_model()
        try:
            agent_id = int(request.POST.get("agent_id", ""))
        except (TypeError, ValueError):
            agent_id = None

        cible = Agent.objects.filter(pk=agent_id, direction=direction).first() if agent_id else None
        profil = (request.POST.get("profil") or "").strip()
        actif = request.POST.get("actif") == "1"

        if not cible:
            messages.error(request, "Agent introuvable.")
        elif actif and profil not in catalogue_profils:
            messages.error(request, "Profil invalide.")
        else:
            definir_acces(cible, code_application, profil, actif, accorde_par=request.user)
            logger.info(
                "Accès %s : %s -> profil=%r actif=%s (par %s)",
                code_application,
                cible.matricule,
                profil,
                actif,
                request.user.matricule,
            )
            messages.success(request, f"Accès mis à jour pour {cible.display_name()}.")
        return redirect(request.path)

    lignes = acces_de_la_direction(direction, code_application)
    return render(
        request,
        template_name,
        {"lignes": lignes, "profils": catalogue_profils, "code_application": code_application},
    )
