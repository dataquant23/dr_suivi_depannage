"""Catalogue des profils de l'application dépannage.

`{nom_profil: {"description", "droits"}}`, interprété via
`core.services.acces.a_le_droit`. L'accès effectif vit dans
`core.AccesApplication`.

  - Dépanneur     : saisie terrain.
  - Agent DCRD    : mêmes droits de saisie, périmètre DC.
  - Responsable   : supervision, délais, clôtures.
  - Administration : Responsable + gestion du périmètre des agents.
"""
from __future__ import annotations

PROFILS: dict[str, dict] = {
    "Dépanneur": {
        "description": "Saisie terrain : ouverture et clôture des dossiers de dépannage (périmètre DR).",
        "droits": ["acces", "saisir"],
    },
    "Agent DCRD": {
        "description": "Activités transmises à la Direction Centrale Réseau Distribution : "
        "mêmes droits de saisie qu'un dépanneur, périmètre DC.",
        "droits": ["acces", "saisir", "dcrd"],
    },
    "Responsable": {
        "description": "Supervision : alertes, délais, clôture des deux périmètres (DR et DC).",
        "droits": ["acces", "saisir", "responsable"],
    },
    "Administration": {
        "description": "Tout Responsable, plus la gestion du périmètre géographique des agents.",
        "droits": ["acces", "saisir", "responsable", "admin"],
    },
}
