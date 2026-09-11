"""
Analyse et validation des entrées `DR_HOTES_SSO`.

Cas réel visé : `dran.dxteriz.com` héberge DRAN à la racine ;
`innovation.dxteriz.com` héberge plusieurs applications indépendantes sous des
préfixes de chemin, dont seules certaines partagent la connexion avec DRAN.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from core.sso import hotes, parse_entree, parse_entrees, url_autorisee


class ParseEntreeTests(SimpleTestCase):
    def test_hote_seul(self):
        self.assertEqual(parse_entree("dran.dxteriz.com"), ("dran.dxteriz.com", ""))

    def test_hote_avec_prefixe(self):
        self.assertEqual(
            parse_entree("innovation.dxteriz.com/navig_poste"),
            ("innovation.dxteriz.com", "/navig_poste"),
        )

    def test_barre_finale_ignoree(self):
        self.assertEqual(
            parse_entree("innovation.dxteriz.com/navig_poste/"),
            ("innovation.dxteriz.com", "/navig_poste"),
        )

    def test_espaces_ignores(self):
        self.assertEqual(parse_entree("  dran.dxteriz.com  "), ("dran.dxteriz.com", ""))

    def test_entree_vide(self):
        self.assertEqual(parse_entree(""), ("", ""))


class HotesTests(SimpleTestCase):
    def test_deduplique_les_hotes_repetes(self):
        entrees = [
            "innovation.dxteriz.com/navig_poste",
            "innovation.dxteriz.com/quartier_hors_tension",
            "dran.dxteriz.com",
        ]
        self.assertEqual(hotes(entrees), ["innovation.dxteriz.com", "dran.dxteriz.com"])

    def test_liste_vide(self):
        self.assertEqual(hotes([]), [])
        self.assertEqual(hotes(None), [])

    def test_ignore_les_entrees_vides(self):
        self.assertEqual(hotes(["", "  ", "dran.dxteriz.com"]), ["dran.dxteriz.com"])


class UrlAutoriseeTests(SimpleTestCase):
    ENTREES = [
        "dran.dxteriz.com",
        "innovation.dxteriz.com/navig_poste",
    ]

    def _autorisee(self, url: str) -> bool:
        return url_autorisee(
            url, hote_courant="dran.dxteriz.com", entrees=self.ENTREES, https_requis=True
        )

    def test_meme_hote_toujours_autorise(self):
        for chemin in ("/visite_client/", "/retablissements/", "/n_importe_quoi/"):
            with self.subTest(chemin=chemin):
                self.assertTrue(self._autorisee(f"https://dran.dxteriz.com{chemin}"))

    def test_chemin_relatif_autorise(self):
        self.assertTrue(self._autorisee("/visite_client/"))

    def test_application_declaree_avec_prefixe_autorisee(self):
        self.assertTrue(self._autorisee("https://innovation.dxteriz.com/navig_poste/"))
        self.assertTrue(self._autorisee("https://innovation.dxteriz.com/navig_poste/tableau/42"))

    def test_prefixe_exact_sans_barre_finale_autorise(self):
        self.assertTrue(self._autorisee("https://innovation.dxteriz.com/navig_poste"))

    def test_application_non_declaree_refusee(self):
        """L'application n'a pas déclaré vouloir participer au SSO : elle ne doit rien recevoir."""
        self.assertFalse(self._autorisee("https://innovation.dxteriz.com/quartier_hors_tension/"))

    def test_racine_de_l_hote_non_couverte_par_un_prefixe_refusee(self):
        self.assertFalse(self._autorisee("https://innovation.dxteriz.com/"))

    def test_prefixe_partiel_non_confondu(self):
        """« /navig_poste_bis » ne doit pas être confondu avec « /navig_poste »."""
        self.assertFalse(self._autorisee("https://innovation.dxteriz.com/navig_poste_bis/"))

    def test_hote_totalement_inconnu_refuse(self):
        self.assertFalse(self._autorisee("https://autre-domaine.ci/"))

    def test_redirection_ouverte_refusee(self):
        for cible in (
            "https://evil.example.com/vol",
            "//evil.example.com/vol",
            "https://dran.dxteriz.com.evil.example.com/",
            "http://innovation.dxteriz.com.attaquant.ci/navig_poste/",
            "javascript:alert(1)",
        ):
            with self.subTest(cible=cible):
                self.assertFalse(self._autorisee(cible))

    def test_url_vide_refusee(self):
        self.assertFalse(self._autorisee(""))

    def test_hote_bare_couvre_tous_les_chemins(self):
        """Rétrocompatibilité : un hôte déclaré sans préfixe garde son ancien comportement."""
        entrees = ["innovation.dxteriz.com"]
        for chemin in ("/", "/n_importe_quoi/", "/navig_poste/"):
            with self.subTest(chemin=chemin):
                self.assertTrue(
                    url_autorisee(
                        f"https://innovation.dxteriz.com{chemin}",
                        hote_courant="dran.dxteriz.com",
                        entrees=entrees,
                        https_requis=True,
                    )
                )

    def test_https_requis_bloque_le_http(self):
        self.assertFalse(
            url_autorisee(
                "http://innovation.dxteriz.com/navig_poste/",
                hote_courant="dran.dxteriz.com",
                entrees=self.ENTREES,
                https_requis=True,
            )
        )

    def test_plusieurs_prefixes_sur_le_meme_hote(self):
        entrees = [
            "innovation.dxteriz.com/navig_poste",
            "innovation.dxteriz.com/quartier_hors_tension",
        ]
        for chemin, attendu in (
            ("/navig_poste/x", True),
            ("/quartier_hors_tension/y", True),
            ("/autre_appli/z", False),
        ):
            with self.subTest(chemin=chemin):
                self.assertEqual(
                    url_autorisee(
                        f"https://innovation.dxteriz.com{chemin}",
                        hote_courant="dran.dxteriz.com",
                        entrees=entrees,
                        https_requis=True,
                    ),
                    attendu,
                )
