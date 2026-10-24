# -*- coding: utf-8 -*-
"""Tests de legifrance.py qui ne demandent ni réseau ni identifiants PISTE.

Lancement, depuis la racine du dépôt :
    python -m unittest discover -s connecteurs -v
"""
import unittest

import legifrance


class NumerosCherches(unittest.TestCase):
    """_art_candidates : les numéros essayés auprès de Légifrance, du plus précis au plus général."""

    ATTENDUS = {
        "L. 314-11 8°": ["L314-11", "L314"],
        "158-5-a": ["158-5-a", "158-5", "158"],
        "L. 181-18": ["L181-18", "L181"],
        "R. 122-5": ["R122-5", "R*122-5", "R122", "R*122"],
        "6": ["6"],
        "": [],
        None: [],
    }

    def test_designations_sans_prefixe(self):
        for article, attendu in self.ATTENDUS.items():
            with self.subTest(article=article):
                self.assertEqual(legifrance._art_candidates(article), attendu)

    def test_prefixe_article_retire(self):
        for article in ["Article L. 181-18", "article L. 181-18", "ARTICLE L. 181-18",
                        "art. L. 181-18", "Art. L. 181-18", "art L. 181-18", "art.L. 181-18",
                        "l'article L. 181-18", "l’article L. 181-18", "  Article  L. 181-18 "]:
            with self.subTest(article=article):
                self.assertEqual(legifrance._art_candidates(article), ["L181-18", "L181"])

    def test_article_de_loi(self):
        for article in ["article 6", "Article 6", "art. 6"]:
            with self.subTest(article=article):
                self.assertEqual(legifrance._art_candidates(article), ["6"])


class MemeArticle(unittest.TestCase):
    """_meme_article : la désignation demandée et le numéro rendu par Légifrance coïncident-ils ?"""

    IDENTIQUES = [
        ("L. 321-3", "L321-3"),
        ("L. 314-11 8°", "L314-11"),
        ("Article L. 181-18", "L181-18"),
        ("art. L. 181-18", "L181-18"),
        ("l'article R. 181-28", "R181-28"),
        ("article 6", "6"),
        ("Article 6", "6"),
    ]

    DIFFERENTS = [
        ("L. 181-18-1", "L181-18"),
        ("Article L. 181-18-1", "L181-18"),
        ("article 55-1", "55"),
        ("158-5-a", "158"),
        ("", ""),
    ]

    def test_identiques(self):
        for demande, rendu in self.IDENTIQUES:
            with self.subTest(demande=demande, rendu=rendu):
                self.assertTrue(legifrance._meme_article(demande, rendu))

    def test_differents(self):
        for demande, rendu in self.DIFFERENTS:
            with self.subTest(demande=demande, rendu=rendu):
                self.assertFalse(legifrance._meme_article(demande, rendu))


if __name__ == "__main__":
    unittest.main()
