from django import template

from depannages import permissions

register = template.Library()


# --- Rôle de l'agent -------------------------------------------------------
# Le rôle vit dans core.AccesApplication (depannages.permissions) ; ces
# filtres l'exposent aux gabarits.


@register.filter
def peut_saisir(agent):
    return permissions.peut_saisir(agent)


@register.filter
def est_responsable(agent):
    return permissions.est_responsable(agent)


@register.filter
def est_agent_dcrd(agent):
    return permissions.est_agent_dcrd(agent)


@register.filter
def est_admin(agent):
    return permissions.est_admin(agent)


@register.filter
def profil_depannage(agent):
    """Nom du profil dépannage de l'agent (« Dépanneur », « Responsable », ...)."""
    from core.services.acces import profil_de

    return profil_de(agent, "depannages")


@register.filter
def initiales_agent(agent):
    prenoms = (getattr(agent, "prenoms", "") or "").strip()
    nom = (getattr(agent, "nom", "") or "").strip()
    if prenoms or nom:
        return f"{prenoms[:1]}{nom[:1]}".upper()
    return (getattr(agent, "matricule", "") or "??")[:2].upper()


@register.filter
def est_cloture_pour(depannage, structure):
    """Indique si la part de cette structure est deja cloturee."""
    return depannage.est_cloture_pour(structure)


@register.filter
def restante_pour(depannage, structure):
    """Inverse de est_cloture_pour, pour la lisibilite des gabarits."""
    return not depannage.est_cloture_pour(structure)


@register.filter
def peut_cloturer(depannage, utilisateur):
    """Vrai si cet utilisateur a encore une part a cloturer sur ce dossier.

    Sur un dossier multi-structure, une part peut deja etre cloturee cote
    DR et rester ouverte cote DC (ou l inverse) : le bouton Cloturer ne doit
    apparaitre que si le role de l utilisateur correspond a une part
    restante, plutot que se fier uniquement a peut_saisir.
    """
    return bool(depannage.structures_cloturables_par(utilisateur))


@register.filter
def jours_heures(heures):
    """Formate une duree en heures (ex. 51) en 'j h' (ex. '2 j 3 h').

    Reste en heures seules sous 24h, pour ne pas surcharger l affichage
    d un dossier tout juste ouvert.
    """
    if heures is None:
        return "-"
    total = round(heures)
    jours, reste = divmod(total, 24)
    if jours <= 0:
        return f"{reste} h"
    return f"{jours} j {reste} h"
