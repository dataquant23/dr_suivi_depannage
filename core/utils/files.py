"""
Accès disque sécurisé.

L'application Flask construisait des chemins à partir de données utilisateur
(`nom_fichier`, `secteur`) avec de simples `os.path.basename`. Ici, toute
résolution passe par `chemin_sur` qui vérifie que la cible reste **strictement**
sous la racine autorisée (protection contre les traversées de répertoire, y
compris via liens symboliques ou séparateurs Windows).
"""
from __future__ import annotations

import unicodedata
from datetime import datetime
from pathlib import Path

from django.conf import settings

from core.utils.text import human_size, secteur_key


class CheminInterdit(Exception):
    """Levée lorsqu'un chemin sort de la racine autorisée."""


def code_direction(direction=None) -> str:
    """
    Code de la direction régionale à utiliser pour le stockage.

    Accepte une instance `DirectionRegionale`, un code, ou `None` (direction
    par défaut de l'installation).
    """
    if direction is None:
        return settings.DR_CODE_DEFAUT
    code = getattr(direction, "code", direction)
    code = str(code or "").strip().upper()
    if not code or not code.isalnum():
        raise CheminInterdit(f"Code de direction invalide : {direction!r}")
    return code


def racine(cle: str, direction=None) -> Path:
    """
    Racine d'un espace de stockage métier (`impayes`, `paiements`, ...)
    pour une direction régionale donnée.

    Chaque direction dispose de son propre sous-arbre : deux DR hébergées sur
    le même serveur ne peuvent pas lire ni écraser les fichiers de l'autre.
    """
    try:
        sous_dossier = settings.DR_SOUS_DOSSIERS[cle]
    except KeyError as exc:  # pragma: no cover - erreur de programmation
        raise KeyError(f"Espace de stockage inconnu : {cle}") from exc

    base = Path(settings.DR_DATA_ROOT).resolve()
    base.mkdir(parents=True, exist_ok=True)
    chemin = chemin_sur(base, code_direction(direction), sous_dossier)
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def nom_fichier_sur(nom: str) -> str:
    """Nettoie un nom de fichier fourni par l'utilisateur (pas de chemin, pas de contrôle)."""
    nom = unicodedata.normalize("NFKD", str(nom or ""))
    nom = nom.replace("\\", "/").split("/")[-1]
    nom = "".join(c for c in nom if c.isprintable() and c not in '<>:"|?*')
    nom = nom.strip().strip(".")
    return nom[:255]


def chemin_sur(base: Path, *parties: str) -> Path:
    """
    Joint `parties` à `base` et garantit que le résultat reste sous `base`.

    >>> chemin_sur(Path("/data"), "../etc/passwd")
    Traceback (most recent call last):
    CheminInterdit: ...
    """
    base = Path(base).resolve()
    cible = base
    for partie in parties:
        brut = str(partie or "")
        propre = nom_fichier_sur(brut)
        # Un segment doit être un simple nom de fichier : tout séparateur ou
        # référence relative est considéré comme une tentative d'évasion.
        if not propre or propre in {".", ".."} or propre != brut.strip():
            raise CheminInterdit(f"Segment de chemin invalide : {partie!r}")
        cible = cible / propre
    cible = cible.resolve()
    if cible != base and base not in cible.parents:
        raise CheminInterdit(f"Chemin hors de la racine autorisée : {cible}")
    return cible


def dossier_secteur(cle_espace: str, secteur: str, direction=None, creer: bool = True) -> Path:
    """Dossier de stockage d'un secteur, nom normalisé et confiné à sa racine."""
    nom = secteur_key(secteur) or "inconnu"
    dossier = chemin_sur(racine(cle_espace, direction), nom)
    if creer:
        dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def extension_autorisee(nom_fichier: str) -> bool:
    return Path(nom_fichier_sur(nom_fichier)).suffix.lower() in settings.DR_EXTENSIONS_AUTORISEES


def decrit_fichier(chemin: Path) -> dict:
    stat = chemin.stat()
    return {
        "name": chemin.name,
        "size": human_size(stat.st_size),
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        "timestamp": stat.st_mtime,
    }


def liste_fichiers(dossier: Path, extensions: set[str] | None = None) -> list[dict]:
    """Inventaire trié (plus récent d'abord) des fichiers d'un dossier."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    extensions = extensions or settings.DR_EXTENSIONS_AUTORISEES
    fichiers = [
        decrit_fichier(chemin)
        for chemin in dossier.iterdir()
        if chemin.is_file() and chemin.suffix.lower() in extensions
    ]
    return sorted(fichiers, key=lambda item: item["timestamp"], reverse=True)


def vide_dossier(dossier: Path) -> int:
    """Supprime les fichiers d'un dossier (récursivement). Retourne le nombre supprimé."""
    dossier = Path(dossier)
    supprimes = 0
    if not dossier.exists():
        return 0
    for chemin in dossier.rglob("*"):
        if chemin.is_file():
            chemin.unlink()
            supprimes += 1
    return supprimes
