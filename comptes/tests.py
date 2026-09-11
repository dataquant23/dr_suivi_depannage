"""Tests de l'initialisation de compte et du cycle de vie du mot de passe.

Deux familles : parcours nominal, et tests d'intrusion (TestsIntrusion).
"""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.services.acces import definir_acces
from core.services.droits import enregistre_applications

from .services import (
    creer_et_inviter,
    generer_mot_de_passe_provisoire,
    initialiser_mot_de_passe,
)

Agent = get_user_model()

MOT_DE_PASSE_SOLIDE = "Terrain-Cocody-2026!"
AUTRE_MOT_DE_PASSE = "Bingerville-Reseau-77?"


class BaseComptes(TestCase):
    """Registre des applications alimenté, cache vidé entre chaque test
    (le compteur anti-force-brute y vit)."""

    @classmethod
    def setUpTestData(cls):
        # Normalement alimenté par le post_migrate de visite_client, absent ici.
        enregistre_applications()

    def setUp(self):
        cache.clear()

    def creer_agent(self, matricule="agent1", profil="Dépanneur", **extra):
        champs = {
            "nom": extra.pop("nom", "Test"),
            "prenoms": extra.pop("prenoms", "Agent"),
            "email": extra.pop("email", f"{matricule}@exemple.ci"),
        }
        champs.update(extra)
        agent = Agent.objects.create_user(matricule=matricule, password=None, **champs)
        if profil:
            definir_acces(agent, "depannages", profil, True)
        return agent


# ---------------------------------------------------------------------------
# Génération du mot de passe provisoire
# ---------------------------------------------------------------------------


class TestsGenerationMotDePasse(BaseComptes):
    def test_longueur_et_familles_de_caracteres(self):
        mot_de_passe = generer_mot_de_passe_provisoire()
        self.assertGreaterEqual(len(mot_de_passe), 14)
        self.assertTrue(any(c.islower() for c in mot_de_passe))
        self.assertTrue(any(c.isupper() for c in mot_de_passe))
        self.assertTrue(any(c.isdigit() for c in mot_de_passe))
        self.assertTrue(any(not c.isalnum() for c in mot_de_passe))

    def test_pas_de_caracteres_ambigus(self):
        """0/O et 1/l/I sont exclus : le mot de passe est recopié à la main."""
        for _ in range(30):
            self.assertFalse(set(generer_mot_de_passe_provisoire()) & set("0O1lI"))

    def test_deux_tirages_different(self):
        tirages = {generer_mot_de_passe_provisoire() for _ in range(50)}
        self.assertEqual(len(tirages), 50)

    def test_refuse_une_longueur_trop_faible(self):
        with self.assertRaises(ValueError):
            generer_mot_de_passe_provisoire(longueur=8)

    def test_le_mot_de_passe_genere_passe_les_validateurs(self):
        """Un provisoire refusé par l'application serait inutilisable."""
        from django.contrib.auth.password_validation import validate_password

        for _ in range(20):
            validate_password(generer_mot_de_passe_provisoire())


class TestsInitialisation(BaseComptes):
    def test_initialiser_pose_lobligation(self):
        agent = self.creer_agent()
        mot_de_passe = initialiser_mot_de_passe(agent)

        agent.refresh_from_db()
        self.assertTrue(agent.must_change_password)
        self.assertTrue(agent.check_password(mot_de_passe))

    def test_le_mot_de_passe_nest_pas_stocke_en_clair(self):
        agent = self.creer_agent()
        mot_de_passe = initialiser_mot_de_passe(agent)
        agent.refresh_from_db()
        self.assertNotIn(mot_de_passe, agent.password)
        self.assertTrue(agent.password.startswith("pbkdf2_"))

    def test_invitation_envoyee_avec_identifiant_et_mot_de_passe(self):
        agent = self.creer_agent(matricule="kouame")
        mot_de_passe = creer_et_inviter(agent)

        self.assertEqual(len(mail.outbox), 1)
        courriel = mail.outbox[0]
        self.assertEqual(courriel.to, ["kouame@exemple.ci"])
        self.assertIn("kouame", courriel.body)
        self.assertIn(mot_de_passe, courriel.body)
        self.assertIn(reverse("comptes:connexion"), courriel.body)

    def test_renvoyer_les_acces_invalide_lancien_mot_de_passe(self):
        agent = self.creer_agent()
        premier = initialiser_mot_de_passe(agent)
        second = initialiser_mot_de_passe(agent)

        agent.refresh_from_db()
        self.assertFalse(agent.check_password(premier))
        self.assertTrue(agent.check_password(second))


# ---------------------------------------------------------------------------
# Première connexion et changement imposé
# ---------------------------------------------------------------------------


class TestsChangementImpose(BaseComptes):
    def setUp(self):
        super().setUp()
        self.agent = self.creer_agent()
        self.provisoire = initialiser_mot_de_passe(self.agent)

    def test_connexion_avec_provisoire_redirige_vers_le_changement(self):
        reponse = self.client.post(
            reverse("comptes:connexion"),
            {"matricule": self.agent.matricule, "password": self.provisoire},
        )
        self.assertRedirects(
            reponse, reverse("comptes:changer_mot_de_passe") + "?next=%2F"
        )

    def test_toute_autre_page_renvoie_vers_le_changement(self):
        self.client.force_login(self.agent)
        reponse = self.client.get(reverse("depannages:tableau_bord"))
        self.assertRedirects(reponse, reverse("comptes:changer_mot_de_passe"))

    def test_changement_leve_lobligation(self):
        self.client.force_login(self.agent)
        reponse = self.client.post(
            reverse("comptes:changer_mot_de_passe"),
            {"password1": MOT_DE_PASSE_SOLIDE, "password2": MOT_DE_PASSE_SOLIDE},
        )
        self.assertRedirects(reponse, reverse("depannages:tableau_bord"))

        self.agent.refresh_from_db()
        self.assertFalse(self.agent.must_change_password)
        self.assertTrue(self.agent.check_password(MOT_DE_PASSE_SOLIDE))

    def test_la_session_survit_au_changement(self):
        """Sans update_session_auth_hash, l'agent serait déconnecté aussitôt."""
        self.client.force_login(self.agent)
        self.client.post(
            reverse("comptes:changer_mot_de_passe"),
            {"password1": MOT_DE_PASSE_SOLIDE, "password2": MOT_DE_PASSE_SOLIDE},
        )
        reponse = self.client.get(reverse("depannages:tableau_bord"))
        self.assertEqual(reponse.status_code, 200)

    def test_mot_de_passe_trop_court_refuse(self):
        self.client.force_login(self.agent)
        self.client.post(
            reverse("comptes:changer_mot_de_passe"),
            {"password1": "Abc12!", "password2": "Abc12!"},
        )
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.must_change_password)

    def test_confirmation_differente_refusee(self):
        self.client.force_login(self.agent)
        self.client.post(
            reverse("comptes:changer_mot_de_passe"),
            {"password1": MOT_DE_PASSE_SOLIDE, "password2": AUTRE_MOT_DE_PASSE},
        )
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.must_change_password)


class TestsChangementVolontaire(BaseComptes):
    def setUp(self):
        super().setUp()
        self.agent = self.creer_agent()
        self.agent.set_password(MOT_DE_PASSE_SOLIDE)
        self.agent.must_change_password = False
        self.agent.save()

    def test_changement_volontaire(self):
        self.client.force_login(self.agent)
        self.client.post(
            reverse("comptes:changer_mot_de_passe"),
            {"password1": AUTRE_MOT_DE_PASSE, "password2": AUTRE_MOT_DE_PASSE},
        )
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.check_password(AUTRE_MOT_DE_PASSE))


# ---------------------------------------------------------------------------
# Mot de passe oublié
# ---------------------------------------------------------------------------


class TestsReinitialisation(BaseComptes):
    def setUp(self):
        super().setUp()
        self.agent = self.creer_agent(matricule="diallo")
        self.agent.set_password(MOT_DE_PASSE_SOLIDE)
        self.agent.must_change_password = False
        self.agent.save()

    def _lien_depuis_courriel(self):
        corps = mail.outbox[0].body
        trouve = re.search(r"/comptes/mot-de-passe/reinitialiser/[^\s]+", corps)
        self.assertIsNotNone(trouve, "Aucun lien de réinitialisation dans le courriel.")
        return trouve.group(0)

    def test_demande_envoie_un_lien(self):
        self.client.post(
            reverse("comptes:mot_de_passe_oublie"), {"email": self.agent.email}
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_parcours_complet(self):
        self.client.post(
            reverse("comptes:mot_de_passe_oublie"), {"email": self.agent.email}
        )
        lien = self._lien_depuis_courriel()

        reponse = self.client.get(lien)
        self.assertTrue(reponse.context["validlink"])

        self.client.post(
            lien, {"password1": AUTRE_MOT_DE_PASSE, "password2": AUTRE_MOT_DE_PASSE}
        )
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.check_password(AUTRE_MOT_DE_PASSE))

    def test_reinitialisation_leve_lobligation_de_changement(self):
        """Un agent qui a perdu son provisoire passe par « mot de passe oublié »."""
        initialiser_mot_de_passe(self.agent)
        mail.outbox.clear()

        self.client.post(
            reverse("comptes:mot_de_passe_oublie"), {"email": self.agent.email}
        )
        lien = self._lien_depuis_courriel()
        self.client.post(
            lien, {"password1": AUTRE_MOT_DE_PASSE, "password2": AUTRE_MOT_DE_PASSE}
        )

        self.agent.refresh_from_db()
        self.assertFalse(self.agent.must_change_password)

    def test_lien_utilisable_une_seule_fois(self):
        self.client.post(
            reverse("comptes:mot_de_passe_oublie"), {"email": self.agent.email}
        )
        lien = self._lien_depuis_courriel()
        self.client.post(
            lien, {"password1": AUTRE_MOT_DE_PASSE, "password2": AUTRE_MOT_DE_PASSE}
        )

        # Deuxième passage : le jeton a été consommé (le mot de passe a
        # changé) -> lien invalide, renvoyé vers « mot de passe oublié ».
        seconde = self.client.get(lien)
        self.assertRedirects(seconde, reverse("comptes:mot_de_passe_oublie"))

    def test_compte_suspendu_ne_recoit_rien(self):
        self.agent.is_active = False
        self.agent.save(update_fields=["is_active"])
        self.client.post(
            reverse("comptes:mot_de_passe_oublie"), {"email": self.agent.email}
        )
        self.assertEqual(len(mail.outbox), 0)


# ---------------------------------------------------------------------------
# Tests d'intrusion : ce qui doit échouer
# ---------------------------------------------------------------------------


class TestsIntrusion(BaseComptes):
    """Contournements plausibles du dispositif ; tous doivent être bloqués."""

    def setUp(self):
        super().setUp()
        self.agent = self.creer_agent(matricule="cible")
        self.provisoire = initialiser_mot_de_passe(self.agent)

    # --- Force brute ----------------------------------------------------

    def test_blocage_apres_cinq_echecs(self):
        url = reverse("comptes:connexion")
        for _ in range(5):
            self.client.post(url, {"matricule": "cible", "password": "faux"})

        # Même avec le bon mot de passe, le compte est temporairement bloqué.
        reponse = self.client.post(
            url, {"matricule": "cible", "password": self.provisoire}
        )
        self.assertFalse(reponse.context["user"].is_authenticated)
        self.assertContains(reponse, "Trop de tentatives", status_code=429)

    def test_le_blocage_ne_touche_pas_les_autres_comptes(self):
        autre = self.creer_agent(matricule="voisin")
        autre.set_password(MOT_DE_PASSE_SOLIDE)
        autre.must_change_password = False
        autre.save()

        url = reverse("comptes:connexion")
        for _ in range(6):
            self.client.post(url, {"matricule": "cible", "password": "faux"})

        reponse = self.client.post(
            url, {"matricule": "voisin", "password": MOT_DE_PASSE_SOLIDE}, follow=True
        )
        self.assertTrue(reponse.context["user"].is_authenticated)

    # --- Énumération de comptes -----------------------------------------

    def test_message_identique_compte_inconnu_ou_mauvais_mot_de_passe(self):
        url = reverse("comptes:connexion")
        inconnu = self.client.post(url, {"matricule": "personne", "password": "x"})
        connu = self.client.post(url, {"matricule": "cible", "password": "faux"})
        self.assertContains(inconnu, "Identifiants invalides")
        self.assertContains(connu, "Identifiants invalides")

    def test_mot_de_passe_oublie_ne_revele_pas_les_adresses(self):
        connue = self.client.post(
            reverse("comptes:mot_de_passe_oublie"),
            {"email": self.agent.email},
            follow=True,
        )
        inconnue = self.client.post(
            reverse("comptes:mot_de_passe_oublie"),
            {"email": "inexistant@exemple.ci"},
            follow=True,
        )
        # Même destination et même message dans les deux cas : impossible de
        # distinguer un email connu d'un email inconnu (le contenu diffère
        # seulement par le jeton CSRF, propre à chaque requête).
        self.assertEqual(connue.status_code, inconnue.status_code)
        self.assertEqual(connue.redirect_chain, inconnue.redirect_chain)
        self.assertContains(connue, "un lien vient d")
        self.assertContains(inconnue, "un lien vient d")

    # --- Contournement du changement imposé ------------------------------

    def test_impossible_de_lire_les_donnees_sans_changer(self):
        """Le cœur du dispositif : un provisoire ne donne accès à rien."""
        self.client.force_login(self.agent)
        for nom in [
            "depannages:tableau_bord",
            "depannages:travaux_en_cours",
            "depannages:carte",
            "depannages:dossiers_clotures",
        ]:
            reponse = self.client.get(reverse(nom))
            self.assertRedirects(
                reponse,
                reverse("comptes:changer_mot_de_passe"),
                msg_prefix=f"{nom} accessible sous mot de passe provisoire",
            )

    def test_ladmin_django_ne_contourne_pas_lobligation(self):
        """Un admin sous provisoire garderait sinon tous ses droits."""
        admin = self.creer_agent(matricule="chef", profil="Administration")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        initialiser_mot_de_passe(admin)

        self.client.force_login(admin)
        reponse = self.client.get("/admin/")
        self.assertEqual(reponse.status_code, 302)
        self.assertIn(reverse("comptes:changer_mot_de_passe"), reponse["Location"])

    # --- Redirection ouverte ---------------------------------------------

    def test_next_externe_ignore(self):
        """?next=https://site-pirate/ ne doit pas être suivi après connexion."""
        agent = self.creer_agent(matricule="mobile")
        agent.set_password(MOT_DE_PASSE_SOLIDE)
        agent.must_change_password = False
        agent.save()

        reponse = self.client.post(
            reverse("comptes:connexion") + "?next=https://site-pirate.example/",
            {"matricule": "mobile", "password": MOT_DE_PASSE_SOLIDE},
        )
        self.assertNotIn("site-pirate", reponse["Location"])

    def test_next_interne_respecte(self):
        agent = self.creer_agent(matricule="mobile2")
        agent.set_password(MOT_DE_PASSE_SOLIDE)
        agent.must_change_password = False
        agent.save()

        cible = reverse("depannages:carte")
        reponse = self.client.post(
            reverse("comptes:connexion") + f"?next={cible}",
            {"matricule": "mobile2", "password": MOT_DE_PASSE_SOLIDE},
        )
        self.assertEqual(reponse["Location"], cible)

    # --- Jetons de réinitialisation --------------------------------------

    def test_jeton_forge_refuse(self):
        """Un jeton invalide renvoie (sans rendre le formulaire) vers « mot de passe oublié »."""
        uid = urlsafe_base64_encode(force_bytes(self.agent.pk))
        reponse = self.client.get(
            reverse(
                "comptes:mot_de_passe_reinitialiser",
                kwargs={"uidb64": uid, "token": "aaaaaa-bbbbbbbbbbbbbbbbbbbb"},
            ),
        )
        self.assertRedirects(reponse, reverse("comptes:mot_de_passe_oublie"))

    def test_jeton_dun_autre_compte_refuse(self):
        """Le jeton est lié à un utilisateur : le rejouer sur un autre échoue."""
        victime = self.creer_agent(matricule="victime")
        jeton = default_token_generator.make_token(self.agent)
        uid_victime = urlsafe_base64_encode(force_bytes(victime.pk))

        reponse = self.client.get(
            reverse(
                "comptes:mot_de_passe_reinitialiser",
                kwargs={"uidb64": uid_victime, "token": jeton},
            ),
        )
        self.assertRedirects(reponse, reverse("comptes:mot_de_passe_oublie"))

    def test_jeton_invalide_apres_changement_de_mot_de_passe(self):
        jeton = default_token_generator.make_token(self.agent)
        self.agent.set_password(AUTRE_MOT_DE_PASSE)
        self.agent.save()

        uid = urlsafe_base64_encode(force_bytes(self.agent.pk))
        reponse = self.client.get(
            reverse(
                "comptes:mot_de_passe_reinitialiser",
                kwargs={"uidb64": uid, "token": jeton},
            ),
        )
        self.assertRedirects(reponse, reverse("comptes:mot_de_passe_oublie"))

    # --- Contrôle d'accès et CSRF ----------------------------------------

    def test_un_depanneur_ne_peut_pas_creer_de_compte(self):
        agent = self.creer_agent(matricule="simple")
        agent.set_password(MOT_DE_PASSE_SOLIDE)
        agent.must_change_password = False
        agent.save()
        self.client.force_login(agent)

        reponse = self.client.post(
            reverse("referentiel:creer_utilisateur"),
            {
                "matricule": "promu",
                "nom": "Promu",
                "prenoms": "Test",
                "email": "promu@exemple.ci",
                "profil": "Administration",
                "actif": "on",
            },
        )
        self.assertEqual(reponse.status_code, 302)
        self.assertFalse(Agent.objects.filter(matricule="promu").exists())

    def test_un_depanneur_ne_peut_pas_renvoyer_les_acces(self):
        """Sinon il pourrait déclencher un nouveau mot de passe sur un compte admin."""
        agent = self.creer_agent(matricule="simple2")
        agent.set_password(MOT_DE_PASSE_SOLIDE)
        agent.must_change_password = False
        agent.save()
        self.client.force_login(agent)

        ancien = self.agent.password
        reponse = self.client.post(
            reverse("referentiel:renvoyer_acces", args=[self.agent.pk])
        )
        self.assertEqual(reponse.status_code, 302)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.password, ancien)

    @override_settings(CSRF_CHECKS_ENABLED=True)
    def test_changement_de_mot_de_passe_refuse_sans_jeton_csrf(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.agent)
        reponse = client.post(
            reverse("comptes:changer_mot_de_passe"),
            {"password1": MOT_DE_PASSE_SOLIDE, "password2": MOT_DE_PASSE_SOLIDE},
        )
        self.assertEqual(reponse.status_code, 403)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.must_change_password)

    def test_anonyme_ne_peut_pas_changer_de_mot_de_passe(self):
        reponse = self.client.get(reverse("comptes:changer_mot_de_passe"))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("connexion", reponse["Location"])

    def test_compte_suspendu_refuse_meme_avec_le_bon_mot_de_passe(self):
        self.agent.is_active = False
        self.agent.save(update_fields=["is_active"])

        reponse = self.client.post(
            reverse("comptes:connexion"),
            {"matricule": "cible", "password": self.provisoire},
        )
        self.assertFalse(reponse.context["user"].is_authenticated)
