"""Formulaires du socle : connexion, mot de passe, secteurs."""
from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

Agent = get_user_model()


class ConnexionForm(forms.Form):
    matricule = forms.CharField(
        max_length=30,
        strip=True,
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username", "placeholder": "Matricule"}),
    )
    password = forms.CharField(
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Mot de passe"}),
    )

    error_messages = {
        "invalid_login": "Identifiants invalides.",
        "inactive": "Ce compte est désactivé. Contactez l'administrateur.",
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.agent = None
        super().__init__(*args, **kwargs)

    def clean_matricule(self) -> str:
        return (self.cleaned_data["matricule"] or "").replace("\xa0", "").strip()

    def clean(self):
        donnees = super().clean()
        matricule, password = donnees.get("matricule"), donnees.get("password")
        if matricule and password:
            self.agent = authenticate(self.request, username=matricule, password=password)
            if self.agent is None:
                # Message unique : ne révèle pas si le matricule existe.
                raise ValidationError(self.error_messages["invalid_login"], code="invalid_login")
        return donnees


class DefinirMotDePasseForm(forms.Form):
    """Changement / réinitialisation de mot de passe avec règles Django."""

    password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        max_length=128,
    )
    password2 = forms.CharField(
        label="Confirmation",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        max_length=128,
    )

    def __init__(self, agent=None, *args, **kwargs):
        self.agent = agent
        super().__init__(*args, **kwargs)

    def clean_password1(self) -> str:
        mot_de_passe = self.cleaned_data["password1"]
        validate_password(mot_de_passe, self.agent)
        return mot_de_passe

    def clean(self):
        donnees = super().clean()
        p1, p2 = donnees.get("password1"), donnees.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        return donnees

    def save(self, agent=None):
        from django.utils import timezone

        agent = agent or self.agent
        agent.set_password(self.cleaned_data["password1"])
        agent.must_change_password = False
        agent.mot_de_passe_defini_le = timezone.now()
        agent.save(
            update_fields=["password", "must_change_password", "mot_de_passe_defini_le"]
        )
        return agent


class MotDePasseOublieForm(forms.Form):
    email = forms.EmailField(max_length=255, widget=forms.EmailInput(attrs={"autocomplete": "email"}))

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()

    def agent_correspondant(self):
        """Retourne l'agent ou None — la vue répond de façon neutre dans les deux cas."""
        return Agent.objects.filter(email__iexact=self.cleaned_data["email"], is_active=True).first()


class NouvelUtilisateurForm(forms.Form):
    """
    Auto-activation d'un compte par email.

    Réservée aux comptes **jamais encore activés** (mot de passe inutilisable,
    `Agent.objects.create_user(..., password=None)`) : un agent déjà actif ne
    peut pas se faire écraser son mot de passe par ce canal — c'est le rôle de
    « mot de passe oublié », qui a ses propres protections.
    """

    email = forms.EmailField(max_length=255, widget=forms.EmailInput(attrs={"autocomplete": "email"}))

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()

    def agent_a_activer(self):
        """Agent actif, jamais encore activé — ou None si aucune correspondance."""
        agent = Agent.objects.filter(email__iexact=self.cleaned_data["email"], is_active=True).first()
        if agent and not agent.has_usable_password():
            return agent
        return None


class AjouterUtilisateurForm(forms.Form):
    """
    Création d'un agent par un DR/ADR, depuis l'espace de gestion des
    utilisateurs (pas l'admin Django).

    Le mot de passe n'est jamais fixé ici : l'agent créé sans mot de passe
    (`password=None`) l'obtient lui-même via le flux « Nouvel utilisateur ? »
    (email -> mot de passe temporaire), comme pour les agents importés en
    masse. Voir `core.services.authentification.traite_nouvel_utilisateur`.
    """

    matricule = forms.CharField(max_length=30, strip=True, widget=forms.TextInput(attrs={"class": "form-control"}))
    nom = forms.CharField(max_length=80, strip=True, widget=forms.TextInput(attrs={"class": "form-control"}))
    prenoms = forms.CharField(max_length=160, strip=True, widget=forms.TextInput(attrs={"class": "form-control"}))
    fonction = forms.CharField(
        max_length=120, required=False, strip=True, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    site = forms.CharField(
        max_length=120, required=False, strip=True, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    email = forms.EmailField(
        max_length=255, widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"})
    )
    profil = forms.ChoiceField(choices=(), widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.profils import PROFILS

        self.fields["profil"].choices = [(nom, nom) for nom in PROFILS]

    def clean_matricule(self) -> str:
        matricule = (self.cleaned_data["matricule"] or "").replace("\xa0", "").strip()
        if Agent.objects.filter(matricule__iexact=matricule).exists():
            raise ValidationError("Ce matricule est déjà utilisé.")
        return matricule

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if Agent.objects.filter(email__iexact=email).exists():
            raise ValidationError("Cet email est déjà utilisé.")
        return email

    def save(self, direction) -> Agent:
        donnees = self.cleaned_data
        agent = Agent.objects.create_user(
            matricule=donnees["matricule"],
            password=None,
            nom=donnees["nom"],
            prenoms=donnees["prenoms"],
            fonction=donnees.get("fonction", ""),
            site=donnees.get("site", ""),
            email=donnees["email"],
            direction=direction,
        )
        agent.affecter_profil(donnees["profil"])
        from core.services.acces import initialise_acces_defaut

        initialise_acces_defaut(agent)
        return agent


class ChangerProfilForm(forms.Form):
    """Modifie le profil (donc les droits) d'un agent existant."""

    profil = forms.ChoiceField(choices=())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.profils import PROFILS

        self.fields["profil"].choices = [(nom, nom) for nom in PROFILS]


class ChoixSecteurForm(forms.Form):
    """Valide que le secteur soumis appartient bien à la liste autorisée."""

    secteur = forms.CharField(max_length=120)

    def __init__(self, choix: list[str], *args, **kwargs):
        self.choix = choix
        super().__init__(*args, **kwargs)

    def clean_secteur(self) -> str:
        valeur = (self.cleaned_data["secteur"] or "").strip()
        correspondance = {c.lower(): c for c in self.choix}
        if valeur.lower() not in correspondance:
            raise ValidationError("Secteur invalide.")
        return correspondance[valeur.lower()]
