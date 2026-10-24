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


class Pannes(unittest.TestCase):
    """Une panne de PISTE, à chacun des quatre appels, est signalée par le champ `panne`.

    `legifrance.resoudre` et `legifrance._post` sont remplacés par des substituts, les pauses de
    `_retry` sont neutralisées ; identifiants, titres et liens fictifs."""

    TROUVE = {"trouve": True, "exact": True, "id": "LEGIARTI000000000001", "num": "L181-18-1",
              "version_debut": "2017-03-01", "version_fin": None,
              "lien": "https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000000000001"}
    REPONSES = {
        "/consult/getArticle": {"article": {"lienModifications": [
            {"linkType": "CREE", "textCid": "JORFTEXT000000000005", "textTitle": "Loi fictive",
             "natureText": "LOI", "datePubliTexte": "2017-01-01"}]}},
        "/consult/jorf": {"nature": "LOI", "title": "Loi fictive", "prepWork": "<p>Travaux</p>",
                          "dossiersLegislatifs": [{"id": "JORFDOLE000000000006"}]},
        "/consult/dossierLegislatif": {"dossierLegislatif": {
            "arborescence": {"niveaux": [{"libelle": "Assemblée nationale",
                                          "liens": [{"libelle": "Rapport", "lien": "https://exemple.invalid/rapport"}]}]},
            "exposeMotif": "<p>Motifs</p>"}},
    }

    def setUp(self):
        for patch in (mock.patch.object(travaux._time, "sleep"),
                      mock.patch.dict(travaux.legifrance.DERNIERE_PANNE,
                                      {"quand": None, "quoi": None, "nombre": 0})):
            patch.start()
            self.addCleanup(patch.stop)

    def travaux(self, chemin_en_panne=None, resoudre=None):
        def faux_post(chemin, charge):
            if chemin == chemin_en_panne:
                raise RuntimeError("503 Service Unavailable")
            return self.REPONSES[chemin]
        resoudre = resoudre or mock.Mock(return_value=self.TROUVE)
        with mock.patch.object(travaux.legifrance, "resoudre", resoudre), \
             mock.patch.object(travaux.legifrance, "_post", faux_post):
            return travaux.travaux_pour_article("Code de l'environnement", "L. 181-18-1", "2024-03-15")

    def test_sans_panne(self):
        r = self.travaux()
        self.assertTrue(r["trouve"])
        self.assertNotIn("panne", r)
        self.assertEqual(r["travaux_preparatoires"], "Travaux")
        self.assertEqual(len(r["pieces"]), 1)
        self.assertEqual(r["expose_motif"], "Motifs")

    def test_panne_resolution_exception(self):
        r = self.travaux(resoudre=mock.Mock(side_effect=RuntimeError("503 Service Unavailable")))
        self.assertFalse(r["trouve"])
        self.assertIn("503", r["panne"])
        self.assertEqual(r["message"], travaux._MESSAGE_PANNE)

    def test_panne_resolution_signalee(self):
        r = self.travaux(resoudre=mock.Mock(return_value={"trouve": False, "panne": "503 Service Unavailable"}))
        self.assertFalse(r["trouve"])
        self.assertIn("503", r["panne"])
        self.assertEqual(r["message"], travaux._MESSAGE_PANNE)

    def test_panne_article(self):
        r = self.travaux("/consult/getArticle")
        self.assertFalse(r["trouve"])
        self.assertIn("503", r["panne"])
        self.assertIn("version", r)

    def test_panne_texte(self):
        r = self.travaux("/consult/jorf")
        self.assertTrue(r["trouve"])
        self.assertIn("503", r["panne"])
        self.assertEqual(r["travaux_preparatoires"], "")
        self.assertEqual(r["pieces"], [])

    def test_panne_dossier(self):
        r = self.travaux("/consult/dossierLegislatif")
        self.assertTrue(r["trouve"])
        self.assertIn("503", r["panne"])
        self.assertEqual(r["travaux_preparatoires"], "Travaux")
        self.assertEqual(r["pieces"], [])


if __name__ == "__main__":
    unittest.main()
