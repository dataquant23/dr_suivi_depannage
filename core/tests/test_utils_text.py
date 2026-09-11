"""Tests unitaires des normalisations métier (fonctions pures)."""
from __future__ import annotations

from django.test import SimpleTestCase

from core.utils.text import (
    clean_ref_contrat,
    human_size,
    libelle_agent,
    normalise_ref_contrat,
    normalize_payment_sector,
    normalize_phone_ci,
    premier_prenom,
    secteur_key,
    slug_court,
    strip_accents,
)


class SecteurKeyTests(SimpleTestCase):
    def test_supprime_accents_et_separateurs(self):
        self.assertEqual(secteur_key(" adjamé-nord "), "Adjame Nord")
        self.assertEqual(secteur_key("ADJAME_SUD"), "Adjame Sud")
        self.assertEqual(secteur_key("2 plateaux"), "2 Plateaux")

    def test_valeurs_vides(self):
        self.assertEqual(secteur_key(None), "")
        self.assertEqual(secteur_key(""), "")

    def test_idempotence(self):
        une_fois = secteur_key("cocody")
        self.assertEqual(secteur_key(une_fois), une_fois)

    def test_strip_accents(self):
        self.assertEqual(strip_accents("Bingerville Côté Est"), "Bingerville Cote Est")


class TelephoneTests(SimpleTestCase):
    def test_formats_acceptes(self):
        self.assertEqual(normalize_phone_ci("01 02 03 04 05"), "0102030405")
        self.assertEqual(normalize_phone_ci("+225 0102030405"), "0102030405")
        self.assertEqual(normalize_phone_ci("07.08.09.10"), "07080910")

    def test_valeurs_invalides(self):
        for valeur in (None, "", "nan", "NaN", "abc", "123", "010203040506070809"):
            self.assertEqual(normalize_phone_ci(valeur), "", f"valeur={valeur!r}")


class ReferenceContratTests(SimpleTestCase):
    def test_normalisation_complete(self):
        self.assertEqual(normalise_ref_contrat("123456789"), "0123456789000")

    def test_prefixe_et_suffixe_deja_presents(self):
        self.assertEqual(normalise_ref_contrat("012345678000"), "012345678000")

    def test_supprime_caracteres_non_numeriques(self):
        self.assertEqual(clean_ref_contrat("0-12/34 56"), "0123456")

    def test_valeur_vide(self):
        self.assertEqual(normalise_ref_contrat(""), "")


class DiversTests(SimpleTestCase):
    def test_slug_court_borne(self):
        self.assertEqual(slug_court("Adjamé Nord & Sud", 6), "adjame")

    def test_premier_prenom(self):
        self.assertEqual(premier_prenom("Awa Marie Rose"), "Awa")
        self.assertEqual(premier_prenom(None), "")

    def test_libelle_agent(self):
        self.assertEqual(libelle_agent("Kone", "Awa Marie"), "Kone Awa")
        self.assertEqual(libelle_agent("", "", defaut="—"), "—")

    def test_human_size(self):
        self.assertEqual(human_size(0), "0.0 B")
        self.assertEqual(human_size(2048), "2.0 KB")
        self.assertEqual(human_size("illisible"), "0 B")

    def test_normalisation_secteur_paiement(self):
        self.assertEqual(normalize_payment_sector("Agence Djibi"), "Djibi")
        self.assertEqual(normalize_payment_sector("AGENCE ADJAME NORD"), "Adjame Nord")
        self.assertEqual(normalize_payment_sector("Cocody"), "Cocody")
