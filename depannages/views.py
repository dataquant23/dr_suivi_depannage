from collections import Counter, OrderedDict, defaultdict
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from referentiel.models import ParametreDelai, TypeStructure

from . import permissions
from .templatetags.depannage_extras import jours_heures
from .forms import ClotureForm, DepannageForm, RechercheTravauxForm
from .models import (
    CategorieProvisoire,
    Depannage,
    EtatDelai,
    HistoriqueStatut,
    Statut,
    TypeIntervention,
    TypePhoto,
)

COULEURS_CATEGORIE = {
    CategorieProvisoire.COMPTEUR_SHUNTE: "#f97316",
    CategorieProvisoire.SANS_ELECTRICITE: "#dc2626",
    CategorieProvisoire.AUTRE_EQUIPEMENT: "#2563eb",
}


def _travaux_ouverts(user):
    return (
        Depannage.objects.pour_utilisateur(user)
        .en_cours()
        .select_related("secteur", "structure", "cree_par", "commune", "quartier", "sous_quartier")
        .prefetch_related("equipements__structure", "clotures__structure")
    )


# --- Tableau de bord --------------------------------------------------------


def _periode_recap(request):
    periode = request.GET.get("periode", "mois")
    maintenant = timezone.now()

    if periode == "semaine":
        debut = (maintenant - timedelta(days=maintenant.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fin = maintenant
    elif periode == "personnalisee":
        debut = _date(request.GET.get("debut")) or maintenant - timedelta(days=30)
        fin = _date(request.GET.get("fin")) or maintenant
        fin = fin + timedelta(days=1)
    else:
        debut = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        fin = maintenant

    return periode, debut, fin


@login_required
def tableau_bord(request):
    ouverts = list(_travaux_ouverts(request.user))
    periode, debut, fin = _periode_recap(request)
    tous = Depannage.objects.pour_utilisateur(request.user)
    depannages = tous.filter(date_saisie__gte=debut, date_saisie__lte=fin)
    if request.GET.get("secteur"):
        depannages = depannages.filter(secteur_id=request.GET["secteur"])

    par_etat = Counter(d.etat_delai for d in ouverts)
    en_retard = [d for d in ouverts if d.etat_delai == EtatDelai.DEPASSE]
    en_retard.sort(key=lambda d: d.retard_heures, reverse=True)
    total = depannages.count()
    definitifs = depannages.filter(type_intervention=TypeIntervention.DEFINITIF).count()
    a_cloturer = len(ouverts)
    # Une cloture compte dans la periode ou elle a ete faite, pas ou le
    # dossier a ete saisi : un dossier ouvert le mois dernier et cloture
    # aujourd hui doit remonter dans les cloturés d aujourd hui.
    clotures_qs = tous.filter(
        statut__in=[Statut.REGULARISE, Statut.CLOTURE],
        date_regularisation__gte=debut,
        date_regularisation__lte=fin,
    ).prefetch_related("equipements")
    if request.GET.get("secteur"):
        clotures_qs = clotures_qs.filter(secteur_id=request.GET["secteur"])
    clotures_liste = list(clotures_qs)
    durees_cloture = [d.heures_ecoulees for d in clotures_liste if d.heures_ecoulees is not None]
    delai_moyen = round(sum(durees_cloture) / len(durees_cloture)) if durees_cloture else 0
    hors_delai_clotures = sum(
        1
        for d in clotures_liste
        if d.delai_applique_heures and d.heures_ecoulees > d.delai_applique_heures
    )
    # "Compteurs clôturés" : dossiers avec équipement "Compteur", clôturés
    # dans la période. On matche l'équipement (pas categorie_provisoire, vidé
    # pour les définitifs). Cohorte différente du tableau ci-dessous (basé
    # sur les dossiers créés) : les deux peuvent diverger légitimement.
    nb_compteurs_clotures = sum(
        1
        for d in clotures_liste
        if any(e.libelle == "Compteur" for e in d.equipements.all())
    )

    secteurs_matrice = list(permissions.secteurs_autorises(request.user).order_by("code"))
    _, _, cartes_secteur_equipement = _matrice_secteur_equipement(depannages, secteurs_matrice)

    contexte = {
        "rubrique": "tableau_bord",
        "periode": periode,
        "debut": debut,
        "fin": fin,
        "total": total,
        "definitifs": definitifs,
        "nb_nouveaux": tous.filter(date_saisie__gte=timezone.now() - timedelta(days=1)).count(),
        "nb_provisoires": a_cloturer,
        "nb_retard": par_etat[EtatDelai.DEPASSE],
        "nb_bientot": par_etat[EtatDelai.BIENTOT],
        "nb_clotures_mois": len(clotures_liste),
        "delai_moyen": delai_moyen,
        "hors_delai_clotures": hors_delai_clotures,
        "nb_compteurs_clotures": nb_compteurs_clotures,
        "nb_shuntes": sum(1 for d in ouverts if d.est_shunte),
        "nb_sans_electricite": sum(
            1 for d in ouverts if d.categorie_provisoire == CategorieProvisoire.SANS_ELECTRICITE
        ),
        # Plafond large : au-dela, la carte defile (voir .corps-scroll) plutot
        # que de tronquer silencieusement la liste a quelques elements.
        "alertes": en_retard[:30],
        "secteurs_matrice": secteurs_matrice,
        "cartes_secteur_equipement": cartes_secteur_equipement,
        "repartition_secteur": (
            depannages.values("secteur__libelle")
            .annotate(total=Count("id"))
            .order_by("-total")[:8]
        ),
        "par_equipement": (
            depannages.values("equipements__libelle")
            .annotate(total=Count("id"))
            .order_by("-total")[:8]
        ),
        "par_quartier": (
            depannages.filter(quartier__isnull=False)
            .values("quartier__nom", "commune__nom")
            .annotate(total=Count("id"))
            .order_by("-total")[:8]
        ),
        "par_agent": (
            depannages.values("cree_par__nom", "cree_par__prenoms")
            .annotate(total=Count("id"))
            .order_by("-total")[:8]
        ),
        "secteurs": permissions.secteurs_autorises(request.user),
    }
    return render(request, "depannages/tableau_bord.html", contexte)


# --- Saisie terrain ---------------------------------------------------------


@login_required
def saisie(request):
    if not permissions.peut_saisir(request.user):
        messages.error(request, "Votre profil ne permet pas la saisie de dossiers.")
        return redirect("depannages:tableau_bord")

    if request.method == "POST":
        form = DepannageForm(request.POST, request.FILES, utilisateur=request.user)
        if form.is_valid():
            depannage = form.save()
            HistoriqueStatut.objects.create(
                depannage=depannage,
                statut_avant="",
                statut_apres=depannage.statut,
                action="Création de la fiche",
                utilisateur=request.user,
            )
            if depannage.est_provisoire:
                messages.success(request, f"{depannage.numero_bt} enregistré.")
            else:
                messages.success(request, f"{depannage.numero_bt} enregistré (définitif).")
            return redirect("depannages:detail", pk=depannage.pk)
        messages.error(request, "Le formulaire comporte des erreurs.")
    else:
        form = DepannageForm(utilisateur=request.user)

    parametres = ParametreDelai.actuel()
    return render(
        request,
        "depannages/saisie.html",
        {
            "rubrique": "saisie",
            "form": form,
            "parametres": parametres,
            "equipements_par_structure": _grouper_equipements(form),
        },
    )


def _grouper_equipements(form):
    """Regroupe les cases à cocher par structure responsable (DR, DC...)."""
    equipements = {
        str(e.pk): e
        for e in form.fields["equipements"].queryset.select_related("structure")
    }
    groupes = OrderedDict()
    for choix in form["equipements"]:
        equipement = equipements.get(str(choix.data["value"]))
        if equipement is None:
            continue
        libelle = str(choix.choice_label)
        prefixe = f"{equipement.structure.code} - "
        if libelle.startswith(prefixe):
            libelle = libelle[len(prefixe):]
        groupes.setdefault(equipement.structure, []).append(
            {"choix": choix, "libelle": libelle}
        )
    return groupes


# --- Detail et actions ------------------------------------------------------


@login_required
def detail(request, pk):
    depannage = get_object_or_404(
        Depannage.objects.pour_utilisateur(request.user).select_related(
            "secteur", "structure", "cree_par"
        ),
        pk=pk,
    )
    form = ClotureForm(depannage=depannage, utilisateur=request.user)
    autres_sur_ce_bt = (
        Depannage.objects.pour_utilisateur(request.user)
        .filter(numero_bt=depannage.numero_bt)
        .exclude(pk=depannage.pk)[:5]
    )
    return render(
        request,
        "depannages/detail.html",
        {
            "rubrique": "travaux" if depannage.cloture_en_attente else "clotures",
            "depannage": depannage,
            "form": form,
            "photos_ouverture": depannage.photos.filter(
                type_photo__in=[TypePhoto.OUVRAGE, TypePhoto.FICHE_AVIS]
            ),
            "clotures": depannage.clotures.select_related(
                "structure", "cloture_par"
            ).prefetch_related("photos"),
            "structures_restantes": depannage.structures_restantes,
            "peut_cloturer": bool(depannage.structures_cloturables_par(request.user)),
            "historique": depannage.historique.select_related("utilisateur")[:20],
            "autres_sur_ce_bt": autres_sur_ce_bt,
        },
    )


@login_required
def cloturer(request, pk):
    """Passage en définitif : bon de dépannage, photos, responsable de clôture.

    Sur un dossier multi-structure, chaque structure clôture sa part ; le
    dépannage ne devient définitif que lorsque toutes ont clôturé.
    """
    depannage = get_object_or_404(
        Depannage.objects.pour_utilisateur(request.user).select_related(
            "secteur", "structure", "cree_par"
        ),
        pk=pk,
    )

    if not depannage.cloture_en_attente:
        messages.warning(request, "Ce dossier est déjà clôturé.")
        return redirect("depannages:detail", pk=pk)

    cloturables = depannage.structures_cloturables_par(request.user)
    if not cloturables:
        messages.error(
            request,
            "Aucune part à clôturer pour votre profil sur ce dossier. "
            "La structure restante relève d'un autre périmètre.",
        )
        return redirect("depannages:detail", pk=pk)

    if request.method == "POST":
        form = ClotureForm(
            request.POST, request.FILES, depannage=depannage, utilisateur=request.user
        )
        if form.is_valid():
            cloture, cree = form.enregistrer()
            if not cree:
                messages.warning(request, "Cette part était déjà clôturée.")
            elif depannage.statut == Statut.CLOTURE:
                messages.success(
                    request,
                    f"{depannage.numero_bt} clôturé. Toutes les structures "
                    "ont traité leur part : le dépannage est définitif.",
                )
            else:
                restantes = ", ".join(s.code for s in depannage.structures_restantes)
                messages.success(
                    request,
                    f"Part {cloture.structure.code} clôturée. En attente de : {restantes}.",
                )
            return redirect("depannages:detail", pk=pk)
        messages.error(request, "Le formulaire de clôture comporte des erreurs.")
    else:
        form = ClotureForm(depannage=depannage, utilisateur=request.user)

    return render(
        request,
        "depannages/cloture.html",
        {
            "rubrique": "cloture",
            "depannage": depannage,
            "form": form,
            "cloturables": cloturables,
            "deja_cloturees": depannage.clotures.select_related("structure", "cloture_par"),
        },
    )


@login_required
def recherche_cloture(request):
    """Ancienne entrée de clôture : l'action est maintenant dans Travaux en cours."""
    return redirect("depannages:travaux_en_cours")


# --- Travaux en cours -------------------------------------------------------


@login_required
def travaux_en_cours(request):
    form = RechercheTravauxForm(request.GET or None, utilisateur=request.user)
    depannages = _travaux_ouverts(request.user)

    if form.is_valid():
        if form.cleaned_data.get("q"):
            depannages = depannages.filter(numero_bt__icontains=form.cleaned_data["q"].strip())
        if form.cleaned_data.get("secteur"):
            depannages = depannages.filter(secteur_id=form.cleaned_data["secteur"])

    # Les compteurs des onglets (Shuntés / Sans courant / Autres) portent sur
    # les filtres q/secteur/etat mais pas sur l onglet actif lui-même : sinon
    # choisir "Shuntés" ferait retomber les autres compteurs à 0.
    depannages_sans_categorie = list(depannages)
    etat_filtre = form.cleaned_data.get("etat") if form.is_valid() else ""
    if etat_filtre:
        depannages_sans_categorie = [
            d for d in depannages_sans_categorie if d.etat_delai == etat_filtre
        ]
    groupes = OrderedDict(
        (categorie, [d for d in depannages_sans_categorie if d.categorie_provisoire == categorie])
        for categorie in CategorieProvisoire.values
    )

    categorie_filtre = form.cleaned_data.get("categorie") if form.is_valid() else ""
    depannages = (
        depannages_sans_categorie
        if not categorie_filtre
        else groupes[categorie_filtre]
    )

    # Triés par délai décroissant : le dossier ouvert depuis le plus longtemps
    # (donc le plus urgent) remonte en tête de liste.
    depannages.sort(key=lambda d: d.date_saisie)

    etats_secteurs = OrderedDict()
    for depannage in depannages:
        libelle = depannage.secteur.libelle if depannage.secteur_id else "Réseau"
        ligne = etats_secteurs.setdefault(
            libelle,
            {
                "libelle": libelle,
                "total": 0,
                "a_traiter": 0,
                "shuntes": 0,
                "sans_courant": 0,
                "en_retard": 0,
            },
        )
        ligne["total"] += 1
        ligne["a_traiter"] += 1
        if depannage.est_shunte:
            ligne["shuntes"] += 1
        if depannage.categorie_provisoire == CategorieProvisoire.SANS_ELECTRICITE:
            ligne["sans_courant"] += 1
        if depannage.etat_delai == EtatDelai.DEPASSE:
            ligne["en_retard"] += 1

    for ligne in etats_secteurs.values():
        total = max(ligne["total"], 1)
        ligne["pct_a_traiter"] = round(ligne["a_traiter"] * 100 / total)
        ligne["pct_shuntes"] = round(ligne["shuntes"] * 100 / total)
        ligne["pct_sans_courant"] = round(ligne["sans_courant"] * 100 / total)
        ligne["pct_en_retard"] = round(ligne["en_retard"] * 100 / total)

    paginator = Paginator(depannages, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    params_sans_categorie = params.copy()
    params_sans_categorie.pop("categorie", None)

    return render(
        request,
        "depannages/travaux_en_cours.html",
        {
            "rubrique": "travaux",
            "form": form,
            "depannages": page_obj.object_list,
            "page_obj": page_obj,
            "querystring": params.urlencode(),
            "querystring_sans_categorie": params_sans_categorie.urlencode(),
            "categorie_active": form.cleaned_data.get("categorie") if form.is_valid() else "",
            "groupes": groupes,
            "total": len(depannages),
            "nb_shuntes": len(groupes[CategorieProvisoire.COMPTEUR_SHUNTE]),
            "nb_sans_electricite": len(groupes[CategorieProvisoire.SANS_ELECTRICITE]),
            "nb_autres": len(groupes[CategorieProvisoire.AUTRE_EQUIPEMENT]),
            "nb_retard": sum(1 for d in depannages if d.etat_delai == EtatDelai.DEPASSE),
            "libelles_categorie": dict(CategorieProvisoire.choices),
            "etats_secteurs": list(etats_secteurs.values()),
        },
    )


@login_required
def dossiers_clotures(request):
    """Page dédiée : parcourir les dossiers déjà traités (provisoires
    régularisés ou définitifs clôturés), pour en consulter le détail, les
    photos et les pièces de clôture — même périmètre que _travaux_ouverts
    (secteurs/structure autorisés), sans restriction de statut ni de
    type_intervention ici."""
    form = RechercheTravauxForm(request.GET or None, utilisateur=request.user)
    depannages = (
        Depannage.objects.pour_utilisateur(request.user)
        .filter(statut__in=[Statut.REGULARISE, Statut.CLOTURE])
        .select_related("secteur", "structure", "cree_par")
        .prefetch_related("equipements__structure", "clotures__structure", "clotures__cloture_par")
        .order_by("-date_regularisation")
    )
    if form.is_valid():
        if form.cleaned_data.get("q"):
            depannages = depannages.filter(numero_bt__icontains=form.cleaned_data["q"].strip())
        if form.cleaned_data.get("secteur"):
            depannages = depannages.filter(secteur_id=form.cleaned_data["secteur"])

    paginator = Paginator(depannages, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "depannages/dossiers_clotures.html",
        {
            "rubrique": "clotures",
            "form": form,
            "depannages": page_obj.object_list,
            "page_obj": page_obj,
            "querystring": params.urlencode(),
            "total": paginator.count,
        },
    )


# --- Carte ------------------------------------------------------------------


@login_required
def carte(request):
    secteurs = permissions.secteurs_autorises(request.user)
    centre = next((s for s in secteurs if s.latitude and s.longitude), None)
    return render(
        request,
        "depannages/carte.html",
        {
            "rubrique": "carte",
            "secteurs": secteurs,
            "centre_lat": centre.latitude if centre else 5.3600,
            "centre_lon": centre.longitude if centre else -4.0083,
            "categories": CategorieProvisoire.choices,
            "maptiler_key": settings.MAPTILER_KEY,
        },
    )


@login_required
def carte_donnees(request):
    """Points de la carte, filtres et recherche par rayon (JSON)."""
    depannages = _travaux_ouverts(request.user)

    numero_bt = request.GET.get("q", "").strip()
    if numero_bt:
        depannages = depannages.filter(numero_bt__icontains=numero_bt)
    if request.GET.get("secteur"):
        depannages = depannages.filter(secteur_id=request.GET["secteur"])

    lat = _flottant(request.GET.get("lat"))
    lon = _flottant(request.GET.get("lon"))
    rayon = _flottant(request.GET.get("rayon"))

    points, par_zone = [], Counter()
    for depannage in depannages:
        if not depannage.a_position:
            continue
        distance = depannage.distance_km(lat, lon) if lat is not None else None
        if rayon and distance is not None and distance > rayon:
            continue
        libelle_zone = depannage.secteur.libelle if depannage.secteur else "Sans secteur"
        par_zone[libelle_zone] += 1
        points.append(
            {
                "id": depannage.pk,
                "numero_bt": depannage.numero_bt,
                "lat": depannage.latitude,
                "lon": depannage.longitude,
                "secteur": libelle_zone,
                "categorie": depannage.categorie_provisoire,
                "categorie_libelle": depannage.get_categorie_provisoire_display(),
                "couleur": COULEURS_CATEGORIE.get(depannage.categorie_provisoire, "#2563eb"),
                "etat_delai": depannage.etat_delai,
                "structures": [s.code for s in depannage.structures_concernees],
                "equipements": [e.libelle for e in depannage.equipements.all()],
                "heures": round(depannage.heures_ecoulees),
                "delai": depannage.delai_applique_heures,
                "retard": depannage.retard_heures,
                "distance_km": round(distance, 2) if distance is not None else None,
                "url": depannage.get_absolute_url(),
                "url_maps": depannage.url_maps,
            }
        )

    points.sort(key=lambda p: (p["distance_km"] is None, p["distance_km"] or 0))
    return JsonResponse(
        {
            "total": len(points),
            "par_categorie": dict(Counter(p["categorie"] for p in points)),
            "par_zone": dict(par_zone),
            "points": points,
        }
    )


def _flottant(valeur):
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


@login_required
def itineraire(request, pk):
    """Position du user, distance, durée estimée et ouverture dans Maps."""
    depannage = get_object_or_404(Depannage.objects.pour_utilisateur(request.user), pk=pk)
    lat = _flottant(request.GET.get("lat"))
    lon = _flottant(request.GET.get("lon"))
    distance = depannage.distance_km(lat, lon)
    # Estimation prudente en ville : 25 km/h de moyenne.
    duree = round(distance / 25 * 60) if distance else None
    return JsonResponse(
        {
            "numero_bt": depannage.numero_bt,
            "destination": {"lat": depannage.latitude, "lon": depannage.longitude},
            "distance_km": round(distance, 2) if distance else None,
            "duree_min": duree,
            "url_maps": depannage.url_maps,
        }
    )


# --- Récapitulatif ----------------------------------------------------------


def _ligne_matrice(valeurs):
    crees = valeurs["crees"]
    traites = valeurs["traites"]
    taux = round(traites / crees * 100, 1) if crees else None
    if taux is None:
        classe = ""
    elif taux >= 90:
        classe = "vert"
    elif taux >= 70:
        classe = "orange"
    else:
        classe = "rouge"
    # Les delais sont accumules en heures (unite native de l appli) ; le
    # rapport les affiche en jours ET en heures, sur demande explicite.
    delai_moyen_h = (
        sum(valeurs["delais"]) / len(valeurs["delais"]) if valeurs["delais"] else None
    )
    return {
        "crees": crees,
        "traites": traites,
        "taux": taux,
        "classe_taux": classe,
        "delai": round(delai_moyen_h / 24, 1) if delai_moyen_h is not None else None,
        "delai_h": round(delai_moyen_h) if delai_moyen_h is not None else None,
    }


def _matrice_secteur_equipement(depannages, secteurs):
    """Croise secteurs x équipements sur les dossiers provisoires ET
    définitifs (un définitif peut lui aussi être clôturé, immédiatement ou
    après attente d'une autre structure — cf. `cloture_en_attente`) : combien
    de dossiers créés, combien traités (clôturés), taux et délai moyen en
    jours (et non en heures, à la différence du reste de l'appli, pour ce
    rapport).

    Les équipements de structures différentes peuvent porter le même libellé
    (ex. deux "Compteur" distincts côté DR et côté DC) : les cellules sont
    donc indexées par équipement (pk), pas par simple libellé, et regroupées
    par structure — réseau (DR, ex. DRAN) avant clientèle (DC, ex. DCRD),
    comme partout ailleurs dans l'appli.
    """
    def _compteur_vide():
        return {"crees": 0, "traites": 0, "delais": []}

    cellules = defaultdict(_compteur_vide)
    par_secteur = defaultdict(_compteur_vide)
    par_equipement_tous_secteurs = defaultdict(_compteur_vide)
    equipements_par_pk = {}

    for d in depannages.filter(
        secteur__isnull=False
    ).select_related("secteur").prefetch_related("equipements__structure"):
        # "Traité" = plus aucune structure en attente (pas est_ouvert, qui ne
        # couvre que le provisoire).
        ferme = not d.cloture_en_attente
        delai_heures = d.heures_ecoulees if (ferme and d.heures_ecoulees is not None) else None

        par_secteur[d.secteur_id]["crees"] += 1
        if ferme:
            par_secteur[d.secteur_id]["traites"] += 1
            if delai_heures is not None:
                par_secteur[d.secteur_id]["delais"].append(delai_heures)

        for equipement in d.equipements.all():
            equipements_par_pk[equipement.pk] = equipement
            cle = (d.secteur_id, equipement.pk)
            cellules[cle]["crees"] += 1
            if ferme:
                cellules[cle]["traites"] += 1
                if delai_heures is not None:
                    cellules[cle]["delais"].append(delai_heures)

            agrege = par_equipement_tous_secteurs[equipement.pk]
            agrege["crees"] += 1
            if ferme:
                agrege["traites"] += 1
                if delai_heures is not None:
                    agrege["delais"].append(delai_heures)

    total_par_equipement = defaultdict(int)
    for (secteur_id, equipement_pk), valeurs in cellules.items():
        total_par_equipement[equipement_pk] += valeurs["crees"]

    def _cle_tri_equipement(equipement_pk):
        equipement = equipements_par_pk[equipement_pk]
        return (
            equipement.structure.type_structure != TypeStructure.DR,
            equipement.structure.code,
            -total_par_equipement[equipement_pk],
        )

    equipements_tries = sorted(total_par_equipement, key=_cle_tri_equipement)

    lignes_equipement = [
        {
            "libelle": f"{equipements_par_pk[pk].structure.code} · {equipements_par_pk[pk].libelle}",
            "par_secteur": [_ligne_matrice(cellules[(s.pk, pk)]) for s in secteurs],
        }
        for pk in equipements_tries
    ]
    ligne_provisoires = [_ligne_matrice(par_secteur[s.pk]) for s in secteurs]

    def _bloc_secteur(secteur_affiche, cellules_equipement, totaux):
        equipements_secteur = [
            {
                "libelle": equipements_par_pk[pk].libelle,
                "structure": equipements_par_pk[pk].structure.code,
                **_ligne_matrice(cellules_equipement(pk)),
            }
            for pk in equipements_tries
            if cellules_equipement(pk)["crees"]
        ]
        # Pourcentages entiers calculés ici : en fr-fr le template rendrait
        # "50,0" (virgule), invalide dans un style="width:...%".
        crees_max = max((e["crees"] for e in equipements_secteur), default=0) or 1
        for e in equipements_secteur:
            e["pct_crees"] = round(e["crees"] * 100 / crees_max)
            e["pct_taux"] = round(e["taux"]) if e["taux"] is not None else 0
        return {
            "secteur": secteur_affiche,
            "provisoires": _ligne_matrice(totaux),
            "equipements": equipements_secteur,
        }

    # Mêmes données côté secteur (une carte par secteur), précédées d'un bloc
    # agrégé "Tous les secteurs".
    cartes_secteur = [
        _bloc_secteur(
            SimpleNamespace(pk=None, libelle="Tous les secteurs"),
            lambda pk: par_equipement_tous_secteurs[pk],
            {
                "crees": sum(v["crees"] for v in par_secteur.values()),
                "traites": sum(v["traites"] for v in par_secteur.values()),
                "delais": [h for v in par_secteur.values() for h in v["delais"]],
            },
        )
    ]
    for s in secteurs:
        cartes_secteur.append(
            _bloc_secteur(s, lambda pk, s=s: cellules[(s.pk, pk)], par_secteur[s.pk])
        )

    return lignes_equipement, ligne_provisoires, cartes_secteur


@login_required
def recapitulatif(request):
    periode = request.GET.get("periode", "mois")
    maintenant = timezone.now()

    if periode == "semaine":
        debut = (maintenant - timedelta(days=maintenant.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fin = maintenant
    elif periode == "personnalisee":
        debut = _date(request.GET.get("debut")) or maintenant - timedelta(days=30)
        fin = _date(request.GET.get("fin")) or maintenant
        fin = fin + timedelta(days=1)
    else:
        debut = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        fin = maintenant

    depannages = Depannage.objects.pour_utilisateur(request.user).filter(
        date_saisie__gte=debut, date_saisie__lte=fin
    )
    if request.GET.get("secteur"):
        depannages = depannages.filter(secteur_id=request.GET["secteur"])

    total = depannages.count()
    definitifs = depannages.filter(type_intervention=TypeIntervention.DEFINITIF).count()
    provisoires = total - definitifs
    shuntes = depannages.filter(
        categorie_provisoire=CategorieProvisoire.COMPTEUR_SHUNTE
    ).count()

    # Une cloture compte dans la periode ou elle a ete faite, pas ou le
    # dossier a ete saisi : un dossier ouvert avant la periode et cloture
    # dedans doit remonter dans les cloturés de cette periode.
    regularises_qs = Depannage.objects.pour_utilisateur(request.user).filter(
        type_intervention=TypeIntervention.PROVISOIRE,
        date_regularisation__gte=debut,
        date_regularisation__lte=fin,
    )
    if request.GET.get("secteur"):
        regularises_qs = regularises_qs.filter(secteur_id=request.GET["secteur"])
    regularises = list(regularises_qs)
    durees_regularisees = [d.heures_ecoulees for d in regularises if d.heures_ecoulees is not None]
    delai_moyen = (
        round(sum(durees_regularisees) / len(durees_regularisees))
        if durees_regularisees
        else 0
    )
    hors_delai = sum(
        1
        for d in regularises
        if d.delai_applique_heures and d.heures_ecoulees > d.delai_applique_heures
    )

    par_commune = (
        depannages.values("commune__nom").annotate(total=Count("id")).order_by("-total")
    )
    par_quartier = (
        depannages.filter(quartier__isnull=False)
        .values("quartier__nom", "commune__nom")
        .annotate(total=Count("id"))
        .order_by("-total")[:12]
    )
    secteurs_matrice = list(permissions.secteurs_autorises(request.user).order_by("code"))
    lignes_equipement, ligne_provisoires, cartes_secteur = _matrice_secteur_equipement(
        depannages, secteurs_matrice
    )

    # Export demandé : on renvoie le fichier au lieu de la page.
    format_export = request.GET.get("export")
    if format_export == "resume_structures_pdf":
        from .exports import exporter_resume_structures

        return exporter_resume_structures(cartes_secteur, lignes_equipement, debut, fin)
    if format_export == "matrice_excel":
        from .exports import exporter_matrice_secteur_equipement

        return exporter_matrice_secteur_equipement(
            secteurs_matrice, lignes_equipement, ligne_provisoires, debut, fin
        )
    if format_export in {"excel", "pdf", "detail_excel"}:
        return _exporter(
            request, format_export, depannages, debut, fin,
            {
                "total": total, "definitifs": definitifs, "provisoires": provisoires,
                "shuntes": shuntes, "regularises": len(regularises),
                "delai_moyen": delai_moyen, "hors_delai": hors_delai,
            },
            par_commune, par_quartier,
            secteurs_matrice, lignes_equipement,
        )

    contexte = {
        "rubrique": "recap",
        "periode": periode,
        "debut": debut,
        "fin": fin,
        "total": total,
        "definitifs": definitifs,
        "provisoires": provisoires,
        "pct_definitifs": round(definitifs / total * 100) if total else 0,
        "pct_provisoires": round(provisoires / total * 100) if total else 0,
        "shuntes": shuntes,
        "regularises": len(regularises),
        "delai_moyen": delai_moyen,
        "hors_delai": hors_delai,
        "par_secteur": depannages.values("secteur__libelle")
        .annotate(total=Count("id"))
        .order_by("-total"),
        "par_equipement": depannages.values("equipements__libelle")
        .annotate(total=Count("id"))
        .order_by("-total")[:8],
        "par_agent": depannages.values("cree_par__nom", "cree_par__prenoms")
        .annotate(total=Count("id"))
        .order_by("-total")[:8],
        "par_commune": par_commune,
        "par_quartier": par_quartier,
        "secteurs": permissions.secteurs_autorises(request.user),
        "matrice_secteurs": secteurs_matrice,
        "matrice_equipements": lignes_equipement,
        "matrice_provisoires": ligne_provisoires,
        "cartes_secteur_equipement": cartes_secteur,
    }
    return render(request, "depannages/recapitulatif.html", contexte)


def _exporter(
    request, format_export, depannages, debut, fin, chiffres,
    par_commune, par_quartier,
    secteurs_matrice, lignes_equipement,
):
    """Génère le classeur Excel ou le rapport PDF du récapitulatif."""
    from .exports import exporter_detail_dossiers_excel, exporter_excel, exporter_pdf

    dossiers = depannages.select_related(
        "secteur", "commune", "quartier", "sous_quartier", "cree_par"
    ).prefetch_related("equipements__structure", "clotures__cloture_par")

    if format_export == "detail_excel":
        return exporter_detail_dossiers_excel(dossiers, debut, fin)

    resume = [
        ("Chiffres clés", [
            ("Dépannages", chiffres["total"]),
            ("Définitifs", chiffres["definitifs"]),
            ("Dossiers à clôturer", chiffres["provisoires"]),
            ("Compteurs shuntés", chiffres["shuntes"]),
            ("Dossiers clôturés", chiffres["regularises"]),
            ("Délai moyen de clôture", jours_heures(chiffres["delai_moyen"])),
            ("Clôtures hors délai", chiffres["hors_delai"]),
        ]),
    ]

    if format_export == "excel":
        return exporter_excel(dossiers, resume, debut, fin)

    repartitions = [
        ("Répartition par secteur", [
            (l["secteur__libelle"] or "Non rattaché", l["total"])
            for l in depannages.values("secteur__libelle")
            .annotate(total=Count("id")).order_by("-total")
        ]),
        ("Répartition par commune", [
            (l["commune__nom"] or "Hors zone connue", l["total"]) for l in par_commune
        ]),
        ("Répartition par quartier", [
            (f"{l['quartier__nom']} ({l['commune__nom']})", l["total"])
            for l in par_quartier
        ]),
        ("Répartition par équipement", [
            (l["equipements__libelle"], l["total"])
            for l in depannages.values("equipements__libelle")
            .annotate(total=Count("id")).order_by("-total")[:12]
            if l["equipements__libelle"]
        ]),
    ]
    return exporter_pdf(
        resume, debut, fin, repartitions,
        secteurs_matrice, lignes_equipement,
    )


def _date(valeur):
    from django.utils.dateparse import parse_date

    if not valeur:
        return None
    d = parse_date(valeur)
    if not d:
        return None
    return timezone.make_aware(timezone.datetime.combine(d, timezone.datetime.min.time()))


# --- Alertes ----------------------------------------------------------------


@login_required
def alertes(request):
    if not permissions.est_responsable(request.user):
        messages.error(request, "Espace réservé aux responsables.")
        return redirect("depannages:tableau_bord")

    ouverts = list(_travaux_ouverts(request.user))
    depasses = [d for d in ouverts if d.etat_delai == EtatDelai.DEPASSE]
    proches = [d for d in ouverts if d.etat_delai == EtatDelai.BIENTOT]
    depasses.sort(key=lambda d: d.retard_heures, reverse=True)
    proches.sort(key=lambda d: d.pourcentage_delai, reverse=True)

    paginator = Paginator(depasses, 15)
    page_depasses = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "depannages/alertes.html",
        {
            "rubrique": "alertes",
            "depasses": page_depasses.object_list,
            "page_depasses": page_depasses,
            "nb_depasses": len(depasses),
            "proches": proches,
            "parametres": ParametreDelai.actuel(),
        },
    )


@login_required
def recherche(request):
    """Recherche rapide par numéro BT depuis la barre du haut."""
    q = request.GET.get("q", "").strip()
    resultats = []
    if q:
        resultats = (
            Depannage.objects.pour_utilisateur(request.user)
            .filter(Q(numero_bt__icontains=q) | Q(adresse_saisie__icontains=q))
            .select_related("secteur")[:50]
        )
    return render(request, "depannages/recherche.html", {"rubrique": "recherche", "q": q, "resultats": resultats})
