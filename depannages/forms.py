from django import forms
from django.conf import settings

from referentiel.models import Equipement, TypeStructure

from .models import (
    CategorieProvisoire,
    ClotureStructure,
    Depannage,
    OriginePhoto,
    PhotoDepannage,
    TypeIntervention,
    TypePhoto,
)


# --- Champ fichier multiple (patron officiel Django) ------------------------


class SaisieFichiersMultiples(forms.ClearableFileInput):
    allow_multiple_selected = True


class ChampFichiersMultiples(forms.FileField):
    """Accepte plusieurs images pour un meme champ et renvoie une liste."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", SaisieFichiersMultiples())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        nettoyer = super().clean
        if isinstance(data, (list, tuple)):
            return [nettoyer(fichier, initial) for fichier in data]
        if data in self.empty_values:
            return []
        return [nettoyer(data, initial)]


def _verifier_taille(images):
    limite = settings.TAILLE_MAX_PHOTO_MO * 1024 * 1024
    for image in images:
        if image and image.size > limite:
            raise forms.ValidationError(
                f"{image.name} dépasse {settings.TAILLE_MAX_PHOTO_MO} Mo."
            )
    return images


def _enregistrer_photos(depannage, images, type_photo, origine, cloture=None):
    for image in images:
        PhotoDepannage.objects.create(
            depannage=depannage,
            cloture=cloture,
            type_photo=type_photo,
            origine=origine,
            image=image,
        )


# --- Saisie terrain ---------------------------------------------------------


class DepannageForm(forms.ModelForm):
    """Fiche minute : uniquement ce qui permet le suivi.

    Le secteur n est demande que si un equipement DR est coche ; un dossier
    purement reseau (DC) n est pas rattache a un secteur clientele.
    """

    photos_ouvrage = ChampFichiersMultiples(
        label="Photos de l'ouvrage",
        required=True,
        help_text="Plusieurs images possibles.",
    )
    photo_fiche_avis = forms.ImageField(
        label="Photo de la fiche d'avis",
        required=True,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )

    class Meta:
        model = Depannage
        fields = [
            "numero_bt",
            "secteur",
            "type_intervention",
            "categorie_provisoire",
            "equipements",
            "latitude",
            "longitude",
            "precision_m",
            "adresse_saisie",
            "commentaire",
        ]
        widgets = {
            "numero_bt": forms.TextInput(
                attrs={"placeholder": "Ex. 24699", "inputmode": "numeric", "autofocus": True}
            ),
            "type_intervention": forms.RadioSelect,
            # Deduite en JS de la case "Compteur" (+ "shunte") plutot que
            # choisie separement : voir saisie.html (#champ-categorie).
            "categorie_provisoire": forms.HiddenInput,
            "equipements": forms.CheckboxSelectMultiple,
            "latitude": forms.HiddenInput,
            "longitude": forms.HiddenInput,
            "precision_m": forms.HiddenInput,
            "adresse_saisie": forms.TextInput(
                attrs={"placeholder": "Repérage : carrefour, immeuble, poteau..."}
            ),
            "commentaire": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, utilisateur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.utilisateur = utilisateur

        if utilisateur is not None:
            from depannages.permissions import secteurs_autorises

            self.fields["secteur"].queryset = secteurs_autorises(utilisateur)
            self.fields["equipements"].queryset = Equipement.objects.filter(
                actif=True, structure__actif=True
            ).select_related("structure")

        self.fields["type_intervention"].initial = TypeIntervention.PROVISOIRE
        self.fields["type_intervention"].choices = TypeIntervention.choices
        self.fields["categorie_provisoire"].choices = CategorieProvisoire.choices
        self.fields["categorie_provisoire"].required = False
        self.fields["adresse_saisie"].required = False
        self.fields["commentaire"].required = False
        # Rendu obligatoire dynamiquement si un equipement DR est coche.
        self.fields["secteur"].required = False

    def clean_numero_bt(self):
        return self.cleaned_data["numero_bt"].strip().upper()

    def clean_photos_ouvrage(self):
        images = _verifier_taille(self.cleaned_data.get("photos_ouvrage") or [])
        if not images:
            raise forms.ValidationError("Ajouter au moins une photo de l'ouvrage.")
        return images

    def clean_photo_fiche_avis(self):
        image = self.cleaned_data.get("photo_fiche_avis")
        _verifier_taille([image] if image else [])
        return image

    def clean(self):
        donnees = super().clean()
        type_intervention = donnees.get("type_intervention")
        categorie = donnees.get("categorie_provisoire")
        equipements = donnees.get("equipements")

        if type_intervention == TypeIntervention.PROVISOIRE and not categorie:
            self.add_error(
                "categorie_provisoire",
                "Préciser la nature du dossier : shunté, sans électricité ou autre.",
            )
        if type_intervention == TypeIntervention.DEFINITIF:
            # Définitif = clôture de la part du dépanneur dès la saisie ; les
            # photos de l'ouvrage servent de preuve (voir _cloturer_a_la_saisie).
            donnees["categorie_provisoire"] = ""

        if not equipements:
            self.add_error("equipements", "Cocher au moins un équipement.")
        else:
            # Un equipement DR implique un secteur clientele identifiable.
            concerne_dr = any(
                e.structure.type_structure == TypeStructure.DR for e in equipements
            )
            if concerne_dr and not donnees.get("secteur"):
                self.add_error(
                    "secteur",
                    "Un équipement DR est coché : préciser le secteur concerné.",
                )

        if donnees.get("latitude") is None or donnees.get("longitude") is None:
            self.add_error(
                None,
                "Position GPS non captée. Autoriser la localisation ou saisir un repérage.",
            )
        return donnees

    def save(self, commit=True):
        depannage = super().save(commit=False)
        depannage.cree_par = self.utilisateur
        affectation = getattr(self.utilisateur, "affectation_depannage", None)
        depannage.structure = affectation.structure if affectation else None
        if commit:
            depannage.save()
            self.save_m2m()
            origine_ouvrage = (
                OriginePhoto.CAMERA
                if self.data.get("photos_ouvrage_origine") == "CAMERA"
                else OriginePhoto.GALERIE
            )
            _enregistrer_photos(
                depannage,
                self.cleaned_data["photos_ouvrage"],
                TypePhoto.OUVRAGE,
                origine_ouvrage,
            )
            origine_fiche = (
                OriginePhoto.CAMERA
                if self.data.get("photo_fiche_avis_origine") == "CAMERA"
                else OriginePhoto.GALERIE
            )
            _enregistrer_photos(
                depannage,
                [self.cleaned_data["photo_fiche_avis"]],
                TypePhoto.FICHE_AVIS,
                origine_fiche,
            )
            if depannage.type_intervention == TypeIntervention.DEFINITIF:
                self._cloturer_a_la_saisie(depannage)
        return depannage

    def _cloturer_a_la_saisie(self, depannage):
        """Choisir Définitif clôture directement la part du dépanneur : pas
        de second passage par l écran Clôturer pour la structure présente à
        la saisie. Si le dossier concerne aussi une autre structure (ex. DR
        + DC), seule la part que le créateur peut lui-même clôturer est
        traitée ici ; l autre structure retrouve le dossier normalement pour
        clôturer sa propre part plus tard.

        Pas de champ photo séparé pour la preuve de clôture : les "Photos de
        l ouvrage" déjà envoyées (et déjà enregistrées comme TypePhoto.
        OUVRAGE dans save()) sont réutilisées comme preuve de clôture. Leurs
        fichiers ayant déjà été lus une première fois, on doit repositionner
        le curseur de lecture (seek(0)) avant chaque nouvelle sauvegarde.
        """
        origine_ouvrage = (
            OriginePhoto.CAMERA
            if self.data.get("photos_ouvrage_origine") == "CAMERA"
            else OriginePhoto.GALERIE
        )
        photos_ouvrage = self.cleaned_data["photos_ouvrage"]
        for structure in depannage.structures_cloturables_par(self.utilisateur):
            cloture, _cree = depannage.cloturer_structure(structure, self.utilisateur)
            for photo in photos_ouvrage:
                photo.seek(0)
            _enregistrer_photos(
                depannage,
                photos_ouvrage,
                TypePhoto.EQUIPEMENT_CLOTURE,
                origine_ouvrage,
                cloture=cloture,
            )


# --- Clôture ----------------------------------------------------------------


class ClotureForm(forms.Form):
    """Informations de cloture d une part de structure.

    Le bon de depannage et la photo de l equipement remis en etat servent de
    preuve du passage en definitif.
    """

    structure = forms.ChoiceField(label="Structure à clôturer", choices=[])
    bon_depannage = ChampFichiersMultiples(
        label="Image du bon de dépannage", required=False
    )
    photos_equipement = ChampFichiersMultiples(
        label="Photos de l'équipement", required=True, help_text="Plusieurs images possibles."
    )
    commentaire = forms.CharField(
        label="Commentaire de clôture",
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Travaux définitifs réalisés le..."}
        ),
    )

    def __init__(self, *args, depannage=None, utilisateur=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.depannage = depannage
        self.utilisateur = utilisateur
        self.structures_possibles = (
            depannage.structures_cloturables_par(utilisateur) if depannage else []
        )
        self.fields["structure"].choices = [
            (str(s.pk), s.code) for s in self.structures_possibles
        ]
        if len(self.structures_possibles) == 1:
            self.fields["structure"].initial = str(self.structures_possibles[0].pk)

    def clean_structure(self):
        valeur = self.cleaned_data["structure"]
        structure = next(
            (s for s in self.structures_possibles if str(s.pk) == valeur), None
        )
        if structure is None:
            raise forms.ValidationError(
                "Vous ne pouvez pas clôturer la part de cette structure."
            )
        return structure

    def clean_bon_depannage(self):
        return _verifier_taille(self.cleaned_data.get("bon_depannage") or [])

    def clean_photos_equipement(self):
        images = _verifier_taille(self.cleaned_data.get("photos_equipement") or [])
        if not images:
            raise forms.ValidationError("Joindre au moins une photo de l'équipement.")
        return images

    def enregistrer(self):
        structure = self.cleaned_data["structure"]
        cloture, cree = self.depannage.cloturer_structure(
            structure, self.utilisateur, self.cleaned_data.get("commentaire", "")
        )
        if cree:
            _enregistrer_photos(
                self.depannage,
                self.cleaned_data["bon_depannage"],
                TypePhoto.BON_DEPANNAGE,
                OriginePhoto.GALERIE,
                cloture=cloture,
            )
            _enregistrer_photos(
                self.depannage,
                self.cleaned_data["photos_equipement"],
                TypePhoto.EQUIPEMENT_CLOTURE,
                OriginePhoto.CAMERA,
                cloture=cloture,
            )
        return cloture, cree


# --- Filtres ----------------------------------------------------------------


class RechercheTravauxForm(forms.Form):
    """Filtres de l espace Travaux en cours."""

    q = forms.CharField(
        label="N BT / BTA",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Rechercher un numéro BT..."}),
    )
    secteur = forms.ChoiceField(label="Secteur", required=False, choices=[])
    categorie = forms.ChoiceField(
        label="Type",
        required=False,
        choices=[("", "Tous les types")] + list(CategorieProvisoire.choices),
    )
    etat = forms.ChoiceField(
        label="Délai",
        required=False,
        choices=[
            ("", "Tous les délais"),
            ("DEPASSE", "En retard"),
            ("BIENTOT", "Échéance proche"),
            ("OK", "Dans les délais"),
        ],
    )

    def __init__(self, *args, utilisateur=None, **kwargs):
        super().__init__(*args, **kwargs)
        from depannages.permissions import secteurs_autorises

        secteurs = secteurs_autorises(utilisateur) if utilisateur else []
        self.fields["secteur"].choices = [("", "Tous les secteurs")] + [
            (str(s.pk), s.libelle) for s in secteurs
        ]
