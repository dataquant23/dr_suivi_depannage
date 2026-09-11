"""
Normalisation de texte métier (secteurs, téléphones, références contrat).

Ces fonctions sont pures : aucune dépendance à Django ni à la base de données.
Elles sont donc directement testables unitairement.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_ABIDJAN = "Africa/Abidjan"

_NON_DIGITS = re.compile(r"\D+")
_PHONE_NOISE = re.compile(r"[\s .\-()]")
_INDICATIF_CI = re.compile(r"\+?225", re.IGNORECASE)
_VALEURS_VIDES = {"", "nan", "none", "null", "na", "n/a", "#n/a", "nat"}


def strip_accents(value: str) -> str:
    """« Adjamé » -> « Adjame »."""
    decomposed = unicodedata.normalize("NFD", str(value or ""))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def normalize_ascii(value: str) -> str:
    """Minuscules sans accents ni espaces superflus — pour comparer des libellés."""
    return re.sub(r"\s+", " ", strip_accents(value)).strip().lower()


def secteur_key(value: str | None) -> str:
    """
    Clé canonique d'un secteur : sans accent, séparateurs unifiés, capitalisé.

    >>> secteur_key(" adjamé-nord ")
    'Adjame Nord'
    """
    if not value:
        return ""
    texte = strip_accents(str(value))
    texte = re.sub(r"[-_]+", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    return " ".join(mot.capitalize() for mot in texte.split(" "))


def slug_court(value: str, longueur: int = 10) -> str:
    """Slug ASCII borné, utilisé pour fabriquer les codes clients."""
    texte = strip_accents(str(value or "")).strip().lower()
    texte = re.sub(r"[^a-z0-9]+", "-", texte)
    return texte.strip("-")[:longueur] or "x"


def clean_ref_contrat(value: str | None) -> str:
    """Ne conserve que les chiffres d'une référence contrat."""
    if not value:
        return ""
    return _NON_DIGITS.sub("", str(value))


def normalise_ref_contrat(value: str | None) -> str:
    """
    Applique les règles métier : préfixe « 0 », suffixe « 000 », chiffres seulement.

    >>> normalise_ref_contrat("123456789")
    '0123456789000'
    """
    ref = (value or "").strip()
    if not ref:
        return ""
    if not ref.startswith("0"):
        ref = f"0{ref}"
    if not ref.endswith("000"):
        ref = f"{ref}000"
    return clean_ref_contrat(ref)


def prefixe_zero(value: str | None) -> str:
    """Ajoute le zéro initial d'une référence contrat sans autre transformation."""
    ref = (value or "").strip()
    if not ref or ref.startswith("0"):
        return ref
    return f"0{ref}"


def normalize_phone_ci(value) -> str:
    """
    Normalise un numéro ivoirien : retire l'indicatif et la ponctuation.

    Renvoie une chaîne vide si le numéro est inexploitable (au lieu de
    propager « nan » dans les exports, comme le faisait l'application Flask).
    """
    if value is None:
        return ""
    texte = str(value).strip()
    if texte.lower() in _VALEURS_VIDES:
        return ""
    texte = _INDICATIF_CI.sub("", texte)
    texte = _PHONE_NOISE.sub("", texte)
    digits = _NON_DIGITS.sub("", texte)
    if len(digits) == 8:
        return digits
    if len(digits) == 10:
        return digits
    return ""


def premier_prenom(prenoms: str | None) -> str:
    prenoms = (prenoms or "").strip()
    return prenoms.split()[0] if prenoms else ""


def libelle_agent(nom: str | None, prenoms: str | None, defaut: str = "") -> str:
    label = f"{(nom or '').strip()} {premier_prenom(prenoms)}".strip()
    return label or defaut


def human_size(num_bytes) -> str:
    try:
        taille = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    unites = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while taille >= 1024 and index < len(unites) - 1:
        taille /= 1024.0
        index += 1
    return f"{taille:.1f} {unites[index]}"


def tz_now() -> datetime:
    """Heure locale d'Abidjan (aware)."""
    try:
        return datetime.now(ZoneInfo(TZ_ABIDJAN))
    except Exception:  # pragma: no cover - dépend de la base tz du système
        return datetime.now()


def normalize_payment_sector(value: str | None) -> str:
    """Harmonise les libellés secteur des fichiers de paiement (« Agence Djibi » -> « Djibi »)."""
    cle = secteur_key(value)
    correspondances = {
        "Agence Adjame Nord": "Adjame Nord",
        "Agence Adjame Sud": "Adjame Sud",
        "Agence Bingerville": "Bingerville",
        "Agence 2plateaux": "2 Plateaux",
        "Agence 2 Plateaux": "2 Plateaux",
        "Agence De Cocody": "Cocody",
        "Agence Cocody": "Cocody",
        "Agence Djibi": "Djibi",
    }
    return correspondances.get(cle, cle)
