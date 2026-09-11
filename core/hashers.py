"""
Hacheurs de compatibilité avec les mots de passe Werkzeug (application Flask).

Les agents conservent leur mot de passe actuel : à la première connexion
réussie, Django ré-encode automatiquement le mot de passe avec PBKDF2
(`must_update()` renvoie `True`), ce qui fait disparaître le format hérité au
fil des connexions. Aucun mot de passe en clair ne transite ni n'est stocké.
"""
from __future__ import annotations

import base64
import hashlib

from django.contrib.auth.hashers import BasePasswordHasher
from django.utils.crypto import constant_time_compare

FORMAT_SCRYPT = "werkzeug_scrypt"


class WerkzeugScryptPasswordHasher(BasePasswordHasher):
    """
    Vérifie les condensats `scrypt:n:r:p$sel$hex` produits par Werkzeug.

    Stockés sous la forme canonique `werkzeug_scrypt$n$r$p$sel$hex` par la
    commande `migrer_donnees_flask`.
    """

    algorithm = FORMAT_SCRYPT

    def encode(self, password: str, salt: str, n: int = 32768, r: int = 8, p: int = 1) -> str:
        condense = self._derive(password, salt, n, r, p)
        return f"{self.algorithm}${n}${r}${p}${salt}${condense}"

    @staticmethod
    def _derive(password: str, salt: str, n: int, r: int, p: int) -> str:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt.encode("utf-8"),
            n=n,
            r=r,
            p=p,
            maxmem=132 * n * r * p,
        ).hex()

    def decode(self, encoded: str) -> dict:
        algorithme, n, r, p, sel, condense = encoded.split("$", 5)
        assert algorithme == self.algorithm
        return {
            "algorithm": algorithme,
            "n": int(n),
            "r": int(r),
            "p": int(p),
            "salt": sel,
            "hash": condense,
        }

    def verify(self, password: str, encoded: str) -> bool:
        try:
            donnees = self.decode(encoded)
        except (ValueError, AssertionError):
            return False
        attendu = self._derive(password, donnees["salt"], donnees["n"], donnees["r"], donnees["p"])
        return constant_time_compare(attendu, donnees["hash"])

    def must_update(self, encoded: str) -> bool:
        # Toujours vrai : on migre vers PBKDF2 dès la première connexion réussie.
        return True

    def safe_summary(self, encoded: str) -> dict:
        donnees = self.decode(encoded)
        return {
            "algorithme": donnees["algorithm"],
            "paramètres": f"n={donnees['n']} r={donnees['r']} p={donnees['p']}",
            "sel": donnees["salt"][:2] + "…",
            "empreinte": donnees["hash"][:6] + "…",
        }

    def harden_runtime(self, password: str, encoded: str) -> None:  # pragma: no cover
        pass


def convertit_hash_werkzeug(valeur: str) -> tuple[str, bool]:
    """
    Traduit un condensat Werkzeug vers un format compris par Django.

    Retourne `(valeur_stockable, mot_de_passe_a_reinitialiser)`.
      * `pbkdf2:sha256:N$sel$hex` -> `pbkdf2_sha256$N$sel$base64` (identique bit à bit) ;
      * `scrypt:n:r:p$sel$hex`    -> `werkzeug_scrypt$n$r$p$sel$hex` ;
      * tout autre format         -> compte verrouillé (`!`), réinitialisation requise.
    """
    valeur = (valeur or "").strip()
    if not valeur:
        return "!", True

    try:
        entete, sel, condense = valeur.split("$", 2)
        parties = entete.split(":")

        if parties[0] == "pbkdf2" and len(parties) == 3 and parties[1] == "sha256":
            b64 = base64.b64encode(bytes.fromhex(condense)).decode("ascii")
            return f"pbkdf2_sha256${int(parties[2])}${sel}${b64}", False

        if parties[0] == "scrypt" and len(parties) == 4:
            n, r, p = (int(x) for x in parties[1:])
            return f"{FORMAT_SCRYPT}${n}${r}${p}${sel}${condense}", False
    except (ValueError, IndexError):
        pass

    return "!", True
