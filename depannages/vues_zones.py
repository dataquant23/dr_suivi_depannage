"""Analyse territoriale : statistiques et carte par quartier / commune.

Les zones proviennent des polygones OpenStreetMap importes dans `Quartier`.
Chaque depannage est rattache automatiquement a partir de sa position GPS.
"""

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from referentiel.models import NiveauZone, Quartier

from .models import CategorieProvisoire, Depannage, EtatDelai


def _agreger(depannages, cle):
    """Compte par zone : total, shuntes, sans electricite, hors delai."""
    compteurs = defaultdict(
        lambda: {"total": 0, "shuntes": 0, "sans_electricite": 0, "hors_delai": 0,
                 "bientot": 0, "nom": "", "pk": None}
    )
    for depannage in depannages:
        zone = getattr(depannage, cle, None)
        identifiant = zone.pk if zone else None
        ligne = compteurs[identifiant]
        ligne["pk"] = identifiant
        ligne["nom"] = zone.nom if zone else "Hors zone connue"
        ligne["total"] += 1
        if depannage.est_shunte:
            ligne["shuntes"] += 1
        if depannage.categorie_provisoire == CategorieProvisoire.SANS_ELECTRICITE:
            ligne["sans_electricite"] += 1
        etat = depannage.etat_delai
        if etat == EtatDelai.DEPASSE:
            ligne["hors_delai"] += 1
        elif etat == EtatDelai.BIENTOT:
            ligne["bientot"] += 1
    return compteurs


# Niveau demande (parametre ?niveau=) -> (choix NiveauZone, champ Depannage correspondant).
NIVEAUX_URL = {
    "commune": (NiveauZone.COMMUNE, "commune"),
    "quartier": (NiveauZone.QUARTIER, "quartier"),
    "sous_quartier": (NiveauZone.SOUS_QUARTIER, "sous_quartier"),
}


def _travaux_ouverts(user):
    return (
        Depannage.objects.pour_utilisateur(user)
        .en_cours()
        .select_related("secteur", "sous_quartier", "quartier", "commune", "structure")
    )


@login_required
def zones(request):
    """Ancienne analyse separee : la lecture par quartier est fusionnee a la carte."""
    cible = reverse("depannages:carte")
    if request.GET:
        cible += "?" + request.GET.urlencode()
    return redirect(cible)

@login_required
def zones_geojson(request):
    """Contours des zones avec leurs compteurs, pour la carte choroplethe."""
    niveau, cle = NIVEAUX_URL.get(request.GET.get("niveau", "commune"), NIVEAUX_URL["commune"])

    compteurs = _agreger(list(_travaux_ouverts(request.user)), cle)
    # Le lot "hors zone" n est pas dessine : l exclure du calcul d intensite,
    # sinon le degrade des polygones reels serait ecrase.
    maximum = max(
        (l["total"] for identifiant, l in compteurs.items() if identifiant is not None),
        default=0,
    )

    entites = []
    for zone in Quartier.objects.filter(niveau=niveau, actif=True).select_related(
        "commune", "quartier"
    ):
        ligne = compteurs.get(zone.pk)
        total = ligne["total"] if ligne else 0
        entites.append(
            {
                "type": "Feature",
                "geometry": zone.contour,
                "properties": {
                    "pk": zone.pk,
                    "nom": zone.nom,
                    "commune": zone.commune.nom if zone.commune_id else None,
                    "quartier": zone.quartier.nom if zone.quartier_id else None,
                    "niveau": zone.niveau,
                    "total": total,
                    "shuntes": ligne["shuntes"] if ligne else 0,
                    "sans_electricite": ligne["sans_electricite"] if ligne else 0,
                    "hors_delai": ligne["hors_delai"] if ligne else 0,
                    "intensite": round(total / maximum, 3) if maximum else 0,
                    "centre": [zone.centre_lat, zone.centre_lon],
                },
            }
        )

    return JsonResponse(
        {
            "type": "FeatureCollection",
            "maximum": maximum,
            "niveau": niveau,
            "features": entites,
        }
    )
