# -*- coding: utf-8 -*-
"""Tests de legifrance.py qui ne demandent ni réseau ni identifiants PISTE.

Lancement, depuis la racine du dépôt :
    python -m unittest discover -s connecteurs -v
"""
import unittest
from unittest import mock

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


def faux_post(num_rendu):
    """Substitut de `_post` : Légifrance rend toujours l'article `num_rendu`, quel que soit le
    numéro cherché, comme lorsque la cascade retombe sur un article voisin. Identifiants fictifs."""
    def _post(chemin, charge):
        if chemin == "/search" and charge.get("fond") == "LODA_DATE":
            return {"results": [{"titles": [{"id": "LEGITEXT000000000002",
                                             "title": "Loi n° 78-17 du 6 janvier 1978"}]}]}
        if chemin == "/search":
            return {"results": [{"id": "LEGIARTI000000000001"}]}
        if chemin == "/consult/legiPart":
            return {"sections": [{"articles": [{"id": "LEGIARTI000000000003", "num": num_rendu,
                                                "content": "<p>Texte.</p>"}]}]}
        if chemin == "/consult/getArticle":
            return {"article": {"id": charge["id"], "num": num_rendu, "texte": "Texte.",
                                "articleVersions": []}}
        raise AssertionError("appel inattendu : " + chemin)
    return _post


class ResoudreExact(unittest.TestCase):
    """Paramètre `exact` de `resoudre` et `resoudre_loi`, et son usage par `historique_article`.

    `_post` est remplacé par `faux_post` et le catalogue des codes par une liste fixe :
    aucun appel n'atteint PISTE, aucun fichier n'est écrit."""

    CODE = "Code de l'environnement"
    LOI = "loi n° 78-17"

    def setUp(self):
        for patch in (mock.patch.object(legifrance, "_CODES_MAP", {"code de l'environnement": self.CODE}),
                      mock.patch.dict(legifrance._TOC_CACHE, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)

    def resoudre(self, num_rendu, *args, **kwargs):
        with mock.patch.object(legifrance, "_post", faux_post(num_rendu)):
            return legifrance.resoudre(*args, **kwargs)

    def test_code_par_defaut_inexact_rendu(self):
        r = self.resoudre("L181-18", self.CODE, "L. 181-18-1", "2024-03-15")
        self.assertTrue(r["trouve"])
        self.assertFalse(r["exact"])

    def test_code_exact_true_inexact_ecarte(self):
        r = self.resoudre("L181-18", self.CODE, "L. 181-18-1", "2024-03-15", exact=True)
        self.assertFalse(r["trouve"])
        self.assertFalse(r["exact"])
        self.assertEqual(r["num"], "L181-18")
        self.assertEqual(r["lien"], "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000000000001")

    def test_code_exact_true_article_exact_rendu(self):
        r = self.resoudre("L181-18-1", self.CODE, "L. 181-18-1", "2024-03-15", exact=True)
        self.assertTrue(r["trouve"])
        self.assertTrue(r["exact"])

    def test_loi_exact_true_inexact_ecarte(self):
        r = self.resoudre("6", self.LOI, "article 6-1", "2024-03-15", exact=True)
        self.assertFalse(r["trouve"])
        self.assertFalse(r["exact"])
        self.assertEqual(r["num"], "6")

    def test_loi_par_defaut_inexact_rendu(self):
        r = self.resoudre("6", self.LOI, "article 6-1", "2024-03-15")
        self.assertTrue(r["trouve"])
        self.assertFalse(r["exact"])

    def test_historique_inexact_ecarte(self):
        with mock.patch.object(legifrance, "_post", faux_post("L181-18")):
            h = legifrance.historique_article(self.CODE, "L. 181-18-1", "2024-03-15")
        self.assertEqual(h, {"trouve": False, "exact": False, "num": "L181-18",
                             "lien": "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000000000001"})

    def test_historique_exact_poursuivi(self):
        with mock.patch.object(legifrance, "_post", faux_post("L181-18-1")):
            h = legifrance.historique_article(self.CODE, "L. 181-18-1", "2024-03-15")
        self.assertTrue(h["trouve"])
        self.assertEqual(h["versions"], [])


if __name__ == "__main__":
    unittest.main()
