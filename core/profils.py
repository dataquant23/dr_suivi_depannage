"""
Rôles organisationnels et registre des applications du SI.

Historique : ce module portait auparavant la matrice complète des droits
applicatifs (permissions Django partagées entre toutes les applications).
Ce n'est plus le cas : chaque application définit désormais son **propre**
catalogue de profils/droits dans son code (`<app>.profils.PROFILS`), et
l'accès d'un agent à une application donnée vit dans `core.AccesApplication`
(voir `core.services.acces`). Ce module ne garde que :

  * les 5 **rôles organisationnels** (« qui est DR/ADR, RC, agent
    terrain… ») — un rôle par agent, déduit de sa fonction RH, porté par un
    groupe Django comme avant. Il ne donne plus directement de droits
    applicatifs : il sert uniquement à ouvrir l'accès aux écrans
    d'administration (gestion des utilisateurs, gestion des accès de
    chaque application) — voir `core.decorators.org_role_requise`.
  * le registre `core.ApplicationMetier` (nom/description de chaque
    application du SI), toujours utile pour lister les applications et
    compter leurs accès actifs.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Seule permission Django restante : gérer les utilisateurs (identité,
# activation, rôle organisationnel). Tous les autres droits applicatifs sont
# désormais portés par `core.AccesApplication` + le catalogue local de
# chaque application.
# ---------------------------------------------------------------------------
GERER_UTILISATEURS = "core.gerer_utilisateurs"

# ---------------------------------------------------------------------------
# Registre des applications du SI
# ---------------------------------------------------------------------------
# Alimente la table `core.ApplicationMetier`. Chaque application peut être
# déployée dans son propre projet : ce registre reste la référence commune.
APPLICATIONS: dict[str, dict] = {
    "recouvrement": {
        "nom": "Rétablissement / recouvrement client",
        "description": "Impayés, paiements, clients éligibles au rétablissement, réclamations.",
    },
    "visite_client": {
        "nom": "Visite client",
        "description": "Accueil, caisse, plaintes, bilans de caisse et tableaux de bord.",
    },
    "coupure": {
        "nom": "Coupure — Éligibilité coupure",
        "description": "Identification des clients éligibles à la coupure pour impayés, "
        "alertes bons payeurs, clients sensibles, suivi des décisions.",
    },
    "depannages": {
        "nom": "Gestion des dépannages",
        "description": "Suivi terrain des interventions (BT provisoires et définitifs), "
        "délais, alertes et clôtures.",
    },
}

# ---------------------------------------------------------------------------
# Rôles organisationnels (groupes Django) — gate les écrans d'administration
# ---------------------------------------------------------------------------
PROFILS: dict[str, dict] = {
    "Direction régionale": {
        "description": "Directeur régional et adjoints : gère les utilisateurs et les accès "
        "de toutes les applications de sa direction.",
        "permissions": [GERER_UTILISATEURS],
    },
    "Responsable commercial": {
        "description": "Pilotage commercial : gère les accès des applications de sa direction.",
        "permissions": [],
    },
    "Litige et recouvrement": {
        "description": "Agents litige/recouvrement.",
        "permissions": [],
    },
    "Conseiller clientèle": {
        "description": "Accueil et conseil.",
        "permissions": [],
    },
    "Caisse": {
        "description": "Caissiers.",
        "permissions": [],
    },
}

PROFIL_PAR_DEFAUT = "Conseiller clientèle"

# ---------------------------------------------------------------------------
# Rattachement automatique fonction RH -> profil
# ---------------------------------------------------------------------------
# Les clés sont comparées en minuscules et sans accents, par inclusion, dans
# l'ordre ci-dessous (la première correspondance gagne).
FONCTIONS_VERS_PROFIL: list[tuple[str, str]] = [
    ("directeur regional", "Direction régionale"),
    ("adjoint au directeur", "Direction régionale"),
    ("directeur", "Direction régionale"),
    ("responsable commercial", "Responsable commercial"),
    ("responsable", "Responsable commercial"),
    ("litige", "Litige et recouvrement"),
    ("recouvrement", "Litige et recouvrement"),
    ("caiss", "Caisse"),
    ("conseiller", "Conseiller clientèle"),
    ("agent commercial", "Conseiller clientèle"),
]


def profil_pour_fonction(fonction: str | None) -> str:
    """Déduit le rôle organisationnel d'un agent depuis son intitulé de poste."""
    from core.utils.text import normalize_ascii

    libelle = normalize_ascii(fonction or "")
    if not libelle:
        return PROFIL_PAR_DEFAUT
    for motif, profil in FONCTIONS_VERS_PROFIL:
        if motif in libelle:
            return profil
    return PROFIL_PAR_DEFAUT


def permissions_du_profil(profil: str) -> list[str]:
    return list(PROFILS.get(profil, {}).get("permissions", []))
