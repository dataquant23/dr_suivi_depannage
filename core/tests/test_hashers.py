"""Compatibilité des mots de passe hérités de Flask/Werkzeug."""
from __future__ import annotations

import base64
import hashlib

from django.contrib.auth.hashers import check_password, identify_hasher
from django.test import SimpleTestCase, TestCase

from core.hashers import WerkzeugScryptPasswordHasher, convertit_hash_werkzeug

MOT_DE_PASSE = "visite_dran25"


def cree_agent(matricule="AG001", **extra):
    """Agent minimal pour les tests (remplace tests.factories de django_dran)."""
    from django.contrib.auth import get_user_model

    Agent = get_user_model()
    valeurs = {
        "nom": "Kone",
        "prenoms": "Awa Marie",
        "fonction": "Conseiller Client",
        "must_change_password": False,
    }
    valeurs.update(extra)
    return Agent.objects.create_user(matricule=matricule, password=MOT_DE_PASSE, **valeurs)


def hash_werkzeug_scrypt(mot_de_passe: str, sel: str = "AbCdEfGh12345678") -> str:
    n, r, p = 32768, 8, 1
    condense = hashlib.scrypt(
        mot_de_passe.encode(), salt=sel.encode(), n=n, r=r, p=p, maxmem=132 * n * r * p
    ).hex()
    return f"scrypt:{n}:{r}:{p}${sel}${condense}"


def hash_werkzeug_pbkdf2(mot_de_passe: str, sel: str = "SelPbkdf2Test123", iterations: int = 600000) -> str:
    condense = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel.encode(), iterations).hex()
    return f"pbkdf2:sha256:{iterations}${sel}${condense}"


class ConversionHashTests(SimpleTestCase):
    def test_scrypt_verifiable_par_django(self):
        converti, reinitialiser = convertit_hash_werkzeug(hash_werkzeug_scrypt(MOT_DE_PASSE))
        self.assertFalse(reinitialiser)
        self.assertTrue(check_password(MOT_DE_PASSE, converti))
        self.assertFalse(check_password("mauvais", converti))

    def test_pbkdf2_converti_bit_a_bit(self):
        origine = hash_werkzeug_pbkdf2(MOT_DE_PASSE)
        converti, reinitialiser = convertit_hash_werkzeug(origine)
        self.assertFalse(reinitialiser)
        self.assertTrue(converti.startswith("pbkdf2_sha256$"))
        self.assertTrue(check_password(MOT_DE_PASSE, converti))
        # Le condensé est bien le même, seulement ré-encodé en base64.
        hexa = origine.split("$")[2]
        self.assertEqual(converti.split("$")[3], base64.b64encode(bytes.fromhex(hexa)).decode())

    def test_format_inconnu_verrouille_le_compte(self):
        for valeur in ("", None, "md5$abc", "n'importe quoi"):
            converti, reinitialiser = convertit_hash_werkzeug(valeur)
            self.assertTrue(reinitialiser, valeur)
            self.assertEqual(converti, "!")
            self.assertFalse(check_password(MOT_DE_PASSE, converti))

    def test_hasher_declare_dans_les_reglages(self):
        converti, _ = convertit_hash_werkzeug(hash_werkzeug_scrypt(MOT_DE_PASSE))
        self.assertIsInstance(identify_hasher(converti), WerkzeugScryptPasswordHasher)

    def test_resume_sans_secret(self):
        converti, _ = convertit_hash_werkzeug(hash_werkzeug_scrypt(MOT_DE_PASSE))
        resume = WerkzeugScryptPasswordHasher().safe_summary(converti)
        self.assertNotIn(MOT_DE_PASSE, str(resume))
        self.assertTrue(str(resume["empreinte"]).endswith("…"))


class MigrationDepuisHashHeriteTests(TestCase):
    def test_le_hash_herite_est_remplace_a_la_premiere_connexion(self):
        from django.contrib.auth.hashers import get_hasher

        agent = cree_agent("AG800")
        agent.password = convertit_hash_werkzeug(hash_werkzeug_scrypt(MOT_DE_PASSE))[0]
        agent.save(update_fields=["password"])

        self.assertTrue(agent.check_password(MOT_DE_PASSE))
        agent.refresh_from_db()
        # Le hacheur cible est celui configuré en tête de PASSWORD_HASHERS,
        # pas un algorithme figé dans le test.
        self.assertTrue(
            agent.password.startswith(f"{get_hasher().algorithm}$"),
            "le mot de passe hérité doit être ré-encodé automatiquement",
        )
        self.assertTrue(agent.check_password(MOT_DE_PASSE))
