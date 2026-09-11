from django import forms
from django.contrib.auth import get_user_model

from depannages.profils import PROFILS

from .models import AffectationAgent, Equipement, ParametreDelai, Secteur, Structure

Agent = get_user_model()


class ParametreDelaiForm(forms.ModelForm):
    """Délais modifiables par le responsable, avec trace de chaque changement."""

    class Meta:
        model = ParametreDelai
        fields = [
            "delai_compteur_shunte",
            "delai_sans_electricite",
            "delai_autre_equipement",
            "seuil_alerte_pct",
            "appliquer_dossiers_ouverts",
        ]
        widgets = {
            "appliquer_dossiers_ouverts": forms.RadioSelect(
                choices=[(True, "Oui"), (False, "Non")]
            )
        }


class EquipementForm(forms.ModelForm):
    class Meta:
        model = Equipement
        fields = ["structure", "libelle", "code", "categorie", "actif"]


# --- Agents ---------------------------------------------------------------
# Identité : core.Agent (socle partagé). Rôle : core.AccesApplication.
# Périmètre : referentiel.AffectationAgent.


class NouvelAgentForm(forms.Form):
    """Création d'un agent : identité + périmètre + rôle dépannage.

    Sans champ mot de passe : provisoire généré et envoyé par courriel
    (`comptes.services.creer_et_inviter`).
    """

    matricule = forms.CharField(max_length=30, strip=True)
    nom = forms.CharField(max_length=80, strip=True)
    prenoms = forms.CharField(max_length=160, strip=True)
    fonction = forms.CharField(max_length=120, required=False, strip=True)
    email = forms.EmailField(max_length=255)
    telephone = forms.CharField(max_length=30, required=False, strip=True)
    structure = forms.ModelChoiceField(
        queryset=Structure.objects.filter(actif=True), required=False,
        label="Structure de rattachement",
    )
    secteurs = forms.ModelMultipleChoiceField(
        queryset=Secteur.objects.filter(actif=True), required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Laisser vide pour donner accès à tous les secteurs de la structure.",
    )
    profil = forms.ChoiceField(choices=[(nom, nom) for nom in PROFILS])
    actif = forms.BooleanField(required=False, initial=True, label="Accès dépannage actif")

    def clean_matricule(self) -> str:
        matricule = (self.cleaned_data["matricule"] or "").replace("\xa0", "").strip()
        if Agent.objects.filter(matricule__iexact=matricule).exists():
            raise forms.ValidationError("Ce matricule est déjà utilisé.")
        return matricule

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if Agent.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email

    def save(self, accorde_par=None) -> "Agent":
        from core.services.acces import definir_acces

        donnees = self.cleaned_data
        agent = Agent.objects.create_user(
            matricule=donnees["matricule"],
            password=None,
            nom=donnees["nom"],
            prenoms=donnees["prenoms"],
            fonction=donnees.get("fonction", ""),
            email=donnees["email"],
        )
        affectation = AffectationAgent.objects.create(
            agent=agent, structure=donnees.get("structure"), telephone=donnees.get("telephone", "")
        )
        if donnees.get("secteurs"):
            affectation.secteurs.set(donnees["secteurs"])
        definir_acces(agent, "depannages", donnees["profil"], donnees["actif"], accorde_par=accorde_par)
        return agent


class AffectationAgentForm(forms.ModelForm):
    """Modification du périmètre d'un agent déjà créé (pas son identité)."""

    profil = forms.ChoiceField(choices=[(nom, nom) for nom in PROFILS])
    actif = forms.BooleanField(required=False, initial=True, label="Accès dépannage actif")

    class Meta:
        model = AffectationAgent
        fields = ["structure", "secteurs", "telephone"]
        widgets = {"secteurs": forms.CheckboxSelectMultiple}

    def __init__(self, *args, agent=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent = agent
        self.fields["structure"].queryset = Structure.objects.filter(actif=True)
        self.fields["secteurs"].queryset = Secteur.objects.filter(actif=True)
        self.fields["structure"].required = False
        self.fields["secteurs"].required = False
        if agent is not None:
            from core.services.acces import acces_pour

            acces = acces_pour(agent, "depannages")
            self.fields["profil"].initial = acces.profil if acces else ""
            self.fields["actif"].initial = bool(acces and acces.actif)

    def save(self, accorde_par=None, commit=True):
        from core.services.acces import definir_acces

        affectation = super().save(commit=commit)
        definir_acces(
            self.agent,
            "depannages",
            self.cleaned_data["profil"],
            self.cleaned_data["actif"],
            accorde_par=accorde_par,
        )
        return affectation
