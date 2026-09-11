"""
Résolution de la direction régionale courante (multi-DR).

Règles :
  * un agent ne voit que la direction à laquelle il est rattaché ;
  * un compte national (superutilisateur sans direction) voit toutes les
    directions et peut en sélectionner une via la session ;
  * les écrans publics (réclamation client) sont rattachés à la direction
    déduite du contrat, ou à la direction par défaut de l'installation.
"""
from __future__ import annotations

from core.models import DirectionRegionale

CLE_SESSION = "direction_code"


def direction_courante(request) -> DirectionRegionale | None:
    """Direction à appliquer aux lectures et écritures de la requête."""
    utilisateur = getattr(request, "user", None)

    if utilisateur is None or not utilisateur.is_authenticated:
        return DirectionRegionale.par_defaut()

    if utilisateur.voit_toutes_les_directions():
        code = (request.session.get(CLE_SESSION) or "").strip().upper()
        if code:
            return DirectionRegionale.objects.filter(code=code).first()
        return None  # périmètre national : aucune restriction

    return utilisateur.direction or DirectionRegionale.par_defaut()


def direction_pour_ecriture(request) -> DirectionRegionale:
    """
    Direction à affecter à un enregistrement créé pendant la requête.

    Un compte national doit avoir choisi une direction : sans cela, on retombe
    sur la direction par défaut plutôt que d'écrire une donnée orpheline.
    """
    return direction_courante(request) or DirectionRegionale.par_defaut()


def selectionne_direction(request, code: str) -> DirectionRegionale | None:
    """Mémorise la direction consultée par un compte national."""
    direction = DirectionRegionale.objects.filter(code=(code or "").strip().upper(), actif=True).first()
    if direction:
        request.session[CLE_SESSION] = direction.code
    return direction
