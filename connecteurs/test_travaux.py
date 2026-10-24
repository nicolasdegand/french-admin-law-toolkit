# -*- coding: utf-8 -*-
"""Tests de travaux.py qui ne demandent ni réseau ni identifiants PISTE.

Lancement, depuis la racine du dépôt :
    python -m unittest discover -s connecteurs -v
"""
import unittest

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


if __name__ == "__main__":
    unittest.main()
