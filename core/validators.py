"""
Validation des fichiers téléversés.

L'application Flask se contentait de regarder l'extension. On ajoute ici :
  * une taille maximale explicite ;
  * un contrôle de signature binaire (un .xlsx est une archive ZIP « PK »,
    un .xls commence par la signature OLE2) ;
  * le rejet des CSV commençant par `=`, `+`, `-`, `@` (injection de formule
    Excel, dite « CSV injection ») lors des exports.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

SIGNATURE_ZIP = b"PK\x03\x04"
SIGNATURE_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
CARACTERES_FORMULE = ("=", "+", "-", "@", "\t", "\r")


def valide_extension(fichier) -> str:
    extension = Path(getattr(fichier, "name", "") or "").suffix.lower()
    autorisees = settings.DR_EXTENSIONS_AUTORISEES
    if extension not in autorisees:
        raise ValidationError(
            "Format non supporté (%(ext)s). Extensions autorisées : %(ok)s.",
            params={"ext": extension or "inconnu", "ok": ", ".join(sorted(autorisees))},
        )
    return extension


def valide_taille(fichier) -> None:
    taille_max = settings.DR_TAILLE_MAX_UPLOAD
    if getattr(fichier, "size", 0) > taille_max:
        raise ValidationError(
            "Fichier trop volumineux (limite %(mo)s Mo).",
            params={"mo": round(taille_max / (1024 * 1024))},
        )


def valide_signature(fichier, extension: str) -> None:
    """Vérifie que le contenu correspond à l'extension annoncée."""
    position = fichier.tell() if hasattr(fichier, "tell") else 0
    fichier.seek(0)
    entete = fichier.read(8)
    fichier.seek(position)

    if extension == ".xlsx" and not entete.startswith(SIGNATURE_ZIP):
        raise ValidationError("Le fichier .xlsx est corrompu ou n'est pas un vrai classeur Excel.")
    if extension == ".xls" and not (entete.startswith(SIGNATURE_OLE2) or entete.startswith(SIGNATURE_ZIP)):
        raise ValidationError("Le fichier .xls est corrompu ou n'est pas un vrai classeur Excel.")
    if extension == ".csv" and entete.startswith((b"%PDF", b"\x7fELF", b"MZ", SIGNATURE_OLE2)):
        raise ValidationError("Contenu binaire détecté dans un fichier annoncé comme CSV.")


def valide_fichier_tableur(fichier) -> str:
    """Validation complète d'un upload Excel/CSV. Retourne l'extension normalisée."""
    extension = valide_extension(fichier)
    valide_taille(fichier)
    valide_signature(fichier, extension)
    return extension


def neutralise_formule(valeur):
    """
    Préfixe d'une apostrophe les cellules commençant par un caractère de formule.

    Empêche qu'une donnée saisie par un client (« =HYPERLINK(...) ») ne s'exécute
    dans le tableur de l'agent qui ouvre l'export.
    """
    if isinstance(valeur, str) and valeur.startswith(CARACTERES_FORMULE):
        return "'" + valeur
    return valeur
