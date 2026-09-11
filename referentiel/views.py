from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from comptes.services import creer_et_inviter
from depannages import permissions

from .forms import AffectationAgentForm, NouvelAgentForm, ParametreDelaiForm
from .models import AffectationAgent, HistoriqueDelai, ParametreDelai, Secteur

Agent = get_user_model()


def _refuser_si_non_responsable(request):
    if not permissions.est_responsable(request.user):
        messages.error(request, "Espace réservé aux responsables.")
        return redirect("depannages:tableau_bord")
    return None


def _refuser_si_non_admin(request):
    if not permissions.est_admin(request.user):
        messages.error(request, "Seul un administrateur peut gérer les accès.")
        return redirect("depannages:tableau_bord")
    return None


@login_required
def administration(request):
    redirection = _refuser_si_non_responsable(request)
    if redirection:
        return redirection

    return render(
        request,
        "referentiel/administration.html",
        {
            "rubrique": "admin",
            "parametres": ParametreDelai.actuel(),
            "nb_utilisateurs": Agent.objects.filter(is_active=True).count(),
            "nb_secteurs": Secteur.objects.filter(actif=True).count(),
            "historique_delais": HistoriqueDelai.objects.select_related("modifie_par")[:10],
        },
    )


@login_required
def parametres_delais(request):
    redirection = _refuser_si_non_responsable(request)
    if redirection:
        return redirection

    parametres = ParametreDelai.actuel()
    if request.method == "POST":
        form = ParametreDelaiForm(request.POST, instance=parametres)
        if form.is_valid():
            _tracer_modifications(form, request.user)
            parametres = form.save(commit=False)
            parametres.modifie_par = request.user
            parametres.save()

            if parametres.appliquer_dossiers_ouverts:
                nb = _recalculer_dossiers_ouverts(parametres)
                messages.success(
                    request, f"Délais mis à jour. {nb} dossier(s) ouvert(s) recalculé(s)."
                )
            else:
                messages.success(
                    request, "Délais mis à jour pour les nouveaux dossiers."
                )
            return redirect("referentiel:administration")
        messages.error(request, "Vérifier les valeurs saisies.")
    else:
        form = ParametreDelaiForm(instance=parametres)

    return render(
        request,
        "referentiel/delais.html",
        {
            "rubrique": "admin",
            "form": form,
            "parametres": parametres,
            "historique": HistoriqueDelai.objects.select_related("modifie_par")[:20],
        },
    )


def _tracer_modifications(form, utilisateur):
    """Journalise chaque delai modifie : champ, avant, apres, qui, quand."""
    for champ in form.changed_data:
        if champ == "appliquer_dossiers_ouverts":
            continue
        HistoriqueDelai.objects.create(
            champ=form.fields[champ].label or champ,
            ancienne_valeur=str(form.initial.get(champ, "")),
            nouvelle_valeur=str(form.cleaned_data[champ]),
            modifie_par=utilisateur,
        )


def _recalculer_dossiers_ouverts(parametres):
    """Applique les nouveaux delais aux provisoires encore ouverts."""
    from depannages.models import Depannage

    modifies = 0
    for depannage in Depannage.objects.en_cours():
        nouveau = depannage.delai_reference(parametres)
        if nouveau and nouveau != depannage.delai_applique_heures:
            depannage.delai_applique_heures = nouveau
            depannage.save(update_fields=["delai_applique_heures"])
            modifies += 1
    return modifies


# --- Gestion des agents --------------------------------------------------
# Identité core.Agent, rôle core.AccesApplication, périmètre local.


@login_required
def liste_utilisateurs(request):
    redirection = _refuser_si_non_admin(request)
    if redirection:
        return redirection

    from core.models import AccesApplication

    agents = Agent.objects.select_related("affectation_depannage__structure").prefetch_related(
        "affectation_depannage__secteurs"
    )
    # Un administrateur "simple" (accès Administration côté depannages) ne
    # doit pas voir les superutilisateurs (admin django_dran, techniques) :
    # seul un superutilisateur voit les autres superutilisateurs.
    if not request.user.is_superuser:
        agents = agents.filter(is_superuser=False)

    recherche = request.GET.get("q", "").strip()
    if recherche:
        agents = agents.filter(
            Q(matricule__icontains=recherche)
            | Q(nom__icontains=recherche)
            | Q(prenoms__icontains=recherche)
        )

    paginator = Paginator(agents, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    # Requête directe (pas `acces_pour`, qui filtre actif=True) : les accès
    # suspendus doivent rester visibles pour être réactivés.
    acces_par_agent = {
        acces.agent_id: acces
        for acces in AccesApplication.objects.filter(
            application__code="depannages", agent__in=page_obj.object_list
        )
    }
    lignes = [(agent, acces_par_agent.get(agent.pk)) for agent in page_obj.object_list]

    return render(
        request,
        "referentiel/utilisateurs.html",
        {
            "rubrique": "utilisateurs",
            "lignes": lignes,
            "q": recherche,
            "profils": permissions.PROFILS,
            "page_obj": page_obj,
            "querystring": params.urlencode(),
        },
    )


@login_required
def creer_utilisateur(request):
    redirection = _refuser_si_non_admin(request)
    if redirection:
        return redirection

    if request.method == "POST":
        form = NouvelAgentForm(request.POST)
        if form.is_valid():
            agent = form.save(accorde_par=request.user)
            # Le compte n'est utilisable qu'une fois les accès envoyés : si le
            # courriel ne part pas, on le dit franchement plutôt que d'afficher
            # une création réussie qui laisserait l'agent sans identifiants.
            try:
                creer_et_inviter(agent, request=request)
            except Exception as erreur:
                messages.warning(
                    request,
                    f"Compte {agent.matricule} créé, mais l'envoi du courriel "
                    f"a échoué ({erreur}). Utilisez « Renvoyer les accès » une fois "
                    "le problème corrigé.",
                )
            else:
                messages.success(
                    request,
                    f"Compte {agent.matricule} créé. Les identifiants de "
                    f"première connexion ont été envoyés à {agent.email}.",
                )
            return redirect("referentiel:utilisateurs")
        messages.error(request, "Vérifier les informations saisies.")
    else:
        form = NouvelAgentForm()

    return render(
        request, "referentiel/utilisateur_form.html", {"rubrique": "utilisateurs", "form": form, "creation": True}
    )


@login_required
def modifier_utilisateur(request, pk):
    redirection = _refuser_si_non_admin(request)
    if redirection:
        return redirection

    agent = get_object_or_404(Agent, pk=pk)
    affectation = getattr(agent, "affectation_depannage", None) or AffectationAgent(agent=agent)

    if request.method == "POST":
        form = AffectationAgentForm(request.POST, instance=affectation, agent=agent)
        if form.is_valid():
            form.save(accorde_par=request.user)
            messages.success(request, f"Périmètre de {agent.display_name()} mis à jour.")
            return redirect("referentiel:utilisateurs")
        messages.error(request, "Vérifier les informations saisies.")
    else:
        form = AffectationAgentForm(instance=affectation, agent=agent)

    return render(
        request,
        "referentiel/utilisateur_form.html",
        {"rubrique": "utilisateurs", "form": form, "creation": False, "utilisateur_edite": agent},
    )


@login_required
@require_POST
def renvoyer_acces(request, pk):
    """Régénère un mot de passe provisoire et le renvoie par courriel.

    Sert quand l'agent n'a jamais reçu le courriel ou l'a perdu. L'ancien mot
    de passe est invalidé au passage : un courriel d'invitation égaré ne
    reste pas exploitable.
    """
    redirection = _refuser_si_non_admin(request)
    if redirection:
        return redirection

    agent = get_object_or_404(Agent, pk=pk)
    if not agent.email:
        messages.error(
            request,
            f"Le compte {agent.matricule} n'a pas d'adresse e-mail : "
            "renseignez-la d'abord (admin django_dran).",
        )
        return redirect("referentiel:utilisateurs")

    try:
        creer_et_inviter(agent, request=request)
    except Exception as erreur:
        messages.error(request, f"Envoi impossible ({erreur}).")
    else:
        messages.success(
            request,
            f"Nouveaux accès envoyés à {agent.email}. L'ancien mot de "
            "passe ne fonctionne plus.",
        )
    return redirect("referentiel:utilisateurs")


@login_required
@require_POST
def basculer_utilisateur(request, pk):
    """Active/désactive l'accès `depannages` (pas le compte, partagé avec
    les autres applications)."""
    redirection = _refuser_si_non_admin(request)
    if redirection:
        return redirection

    from core.models import AccesApplication
    from core.services.acces import definir_acces

    agent = get_object_or_404(Agent, pk=pk)
    if agent == request.user:
        messages.error(request, "Impossible de suspendre votre propre accès.")
        return redirect("referentiel:utilisateurs")

    # Requête directe : un accès suspendu doit aussi pouvoir être retrouvé.
    acces = AccesApplication.objects.filter(agent=agent, application__code="depannages").first()
    if acces is None:
        messages.error(request, f"{agent.display_name()} n'a pas encore d'accès dépannage à basculer.")
        return redirect("referentiel:utilisateurs")

    definir_acces(agent, "depannages", acces.profil, not acces.actif, accorde_par=request.user)
    etat = "réactivé" if not acces.actif else "suspendu"
    messages.success(request, f"Accès dépannage de {agent.display_name()} {etat}.")
    return redirect("referentiel:utilisateurs")
