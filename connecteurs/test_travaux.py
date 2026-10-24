# -*- coding: utf-8 -*-
"""Tests de travaux.py qui ne demandent ni réseau ni identifiants PISTE.

Lancement, depuis la racine du dépôt :
    python -m unittest discover -s connecteurs -v
"""
import unittest
from unittest import mock

import travaux


class EstReglementaire(unittest.TestCase):
    """_est_reglementaire : un article R. ou D., quelle que soit son écriture."""

    REGLEMENTAIRES = [
        "R. 181-28", "R.181-28", "R181-28", "r. 181-28",
        "D. 123-1", "d. 123-1", "R* 122-1",
        "Article R. 181-28", "article R. 181-28", "ARTICLE R. 181-28", "Article r. 181-28",
        "art. R. 181-28", "Art. R. 181-28", "art. d. 123-1", "art.R. 181-28", "Art R. 181-28",
        "articles R. 181-28 et R. 181-29",
        "l'article R. 181-28", "l’article D. 123-1",
        "art. R. 181-28",          # espaces insécables
        "  R. 181-28  ",
    ]

    NON_REGLEMENTAIRES = [
        "L. 181-18", "l. 181-18", "Article L. 181-18", "art. L. 181-18",
        "LO. 1", "L* 80", "6", "article 6",
        "Règlement", "Décret",
        "", None,
    ]

    def test_reglementaires(self):
        for article in self.REGLEMENTAIRES:
            with self.subTest(article=article):
                self.assertTrue(travaux._est_reglementaire(article))

    def test_non_reglementaires(self):
        for article in self.NON_REGLEMENTAIRES:
            with self.subTest(article=article):
                self.assertFalse(travaux._est_reglementaire(article))


class ArticleInexact(unittest.TestCase):
    """travaux_pour_article demande l'article exact et rend le refus de legifrance.py.

    `legifrance.resoudre` et `legifrance._post` sont remplacés par des substituts :
    aucun appel n'atteint PISTE. Numéros et identifiants fictifs."""

    LIEN = "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000000000001"
    REFUS_INEXACT = {"trouve": False, "exact": False, "num": "L181-18", "lien": LIEN}
    TROUVE_EXACT = {"trouve": True, "exact": True, "id": "LEGIARTI000000000001", "num": "L181-18-1",
                    "version_debut": "2017-03-01", "version_fin": None, "lien": LIEN}

    def test_exact_demande(self):
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=self.REFUS_INEXACT) as resoudre:
            travaux.travaux_pour_article("Code de l'environnement", "L. 181-18-1", "2024-03-15")
        resoudre.assert_called_once_with("Code de l'environnement", "L. 181-18-1", "2024-03-15", exact=True)

    def test_article_inexact_ecarte(self):
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=self.REFUS_INEXACT), \
             mock.patch.object(travaux.legifrance, "_post") as post:
            r = travaux.travaux_pour_article("Code de l'environnement", "L. 181-18-1", "2024-03-15")
        self.assertFalse(r["trouve"])
        self.assertFalse(r["exact"])
        self.assertEqual(r["article"], "L. 181-18-1")
        self.assertEqual(r["num"], "L181-18")
        self.assertEqual(r["lien"], self.LIEN)
        self.assertIn("L181-18", r["message"])
        post.assert_not_called()

    def test_article_absent(self):
        with mock.patch.object(travaux.legifrance, "resoudre", return_value={"trouve": False}):
            r = travaux.travaux_pour_article("Code de l'environnement", "L. 181-18-1", "2024-03-15")
        self.assertNotIn("exact", r)
        self.assertEqual(r["message"], "Version de l'article non résolue à cette date.")

    def test_article_exact_poursuivi(self):
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=self.TROUVE_EXACT), \
             mock.patch.object(travaux.legifrance, "_post", return_value={"article": {}}) as post:
            r = travaux.travaux_pour_article("Code de l'environnement", "L. 181-18-1", "2024-03-15")
        post.assert_called()
        self.assertEqual(r["message"], "Texte créateur de la version non identifié.")

    def test_de_bout_en_bout_avec_legifrance(self):
        """Le vrai `legifrance.resoudre`, PISTE seul simulé : Légifrance rend « L181-18 »."""
        def faux_post(chemin, charge):
            if chemin == "/search":
                return {"results": [{"id": "LEGIARTI000000000001"}]}
            if chemin == "/consult/getArticle":
                return {"article": {"id": charge["id"], "num": "L181-18", "texte": "Texte."}}
            raise AssertionError("appel inattendu : " + chemin)
        with mock.patch.object(travaux.legifrance, "_CODES_MAP",
                               {"code de l'environnement": "Code de l'environnement"}), \
             mock.patch.object(travaux.legifrance, "_post", faux_post):
            r = travaux.travaux_pour_article("Code de l'environnement", "Article L. 181-18-1", "2024-03-15")
        self.assertFalse(r["trouve"])
        self.assertFalse(r["exact"])
        self.assertEqual(r["num"], "L181-18")
        self.assertEqual(r["lien"], self.LIEN)


if __name__ == "__main__":
    unittest.main()
