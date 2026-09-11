from .models import Depannage, EtatDelai


def badges_navigation(request):
    """Compteurs affiches dans la barre laterale et la cloche d'alertes."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    ouverts = list(
        Depannage.objects.pour_utilisateur(user)
        .en_cours()
        .only("date_saisie", "delai_applique_heures", "type_intervention", "statut")
    )
    en_retard = sum(1 for d in ouverts if d.etat_delai == EtatDelai.DEPASSE)
    return {
        "nb_travaux_en_cours": len(ouverts),
        "nb_alertes": en_retard,
    }
