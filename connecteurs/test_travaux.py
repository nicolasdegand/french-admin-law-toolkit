# -*- coding: utf-8 -*-
"""Tests de travaux.py qui ne demandent ni réseau ni identifiants PISTE.

Lancement, depuis la racine du dépôt :
    python -m unittest discover -s connecteurs -v
"""
import ast
import contextlib
import io
import runpy
import sys
import types
import unittest
import urllib.error
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

    `legifrance.resoudre` et `legifrance._post` sont remplacés par des substituts ;
    identifiants, titres et liens fictifs."""

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
        patch = mock.patch.dict(travaux.legifrance.DERNIERE_PANNE, {"quand": None, "quoi": None, "nombre": 0})
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


class Avertissements(unittest.TestCase):
    """Texte créateur ordonnance ou codification : un avertissement dit où chercher. Titres fictifs."""

    def test_nature_et_titre(self):
        cas = [
            ("LOI", "Loi fictive relative à l'environnement", []),
            ("ORDONNANCE", "Ordonnance fictive relative à l'autorisation", [travaux._AVERTISSEMENT_ORDONNANCE]),
            ("ordonnance", "", [travaux._AVERTISSEMENT_ORDONNANCE]),
            (None, "Ordonnance n° 0000-0 fictive", [travaux._AVERTISSEMENT_ORDONNANCE]),
            ("LOI", "Loi fictive portant codification de dispositions", [travaux._AVERTISSEMENT_CODIFICATION]),
            ("ORDONNANCE", "Ordonnance fictive relative à la partie législative du code de l'exemple",
             [travaux._AVERTISSEMENT_ORDONNANCE, travaux._AVERTISSEMENT_CODIFICATION]),
            ("LOI", "Loi fictive modifiant le code de l'exemple", []),
            (None, None, []),
        ]
        for nature, titre, attendu in cas:
            with self.subTest(nature=nature, titre=titre):
                self.assertEqual(travaux._avertissements(nature, titre), attendu)

    def travaux(self, nature, titre):
        reponses = dict(Pannes.REPONSES)
        reponses["/consult/jorf"] = dict(reponses["/consult/jorf"], nature=nature, title=titre)
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=Pannes.TROUVE), \
             mock.patch.object(travaux.legifrance, "_post", lambda chemin, charge: reponses[chemin]):
            return travaux.travaux_pour_article("Code de l'environnement", "L. 181-18-1", "2024-03-15")

    def test_reponse_ordonnance(self):
        r = self.travaux("ORDONNANCE", "Ordonnance fictive relative à l'autorisation")
        self.assertEqual(r["avertissement"], travaux._AVERTISSEMENT_ORDONNANCE)

    def test_reponse_loi(self):
        self.assertNotIn("avertissement", self.travaux("LOI", "Loi fictive"))


class Reessais(unittest.TestCase):
    """Les réessais sont ceux de `legifrance._post` seul : 4 requêtes pour une erreur passagère,
    1 pour une erreur définitive, aucune pause propre à travaux.py.

    `urllib.request.urlopen` est remplacé par un substitut qui répond toujours par l'erreur HTTP
    choisie ; `legifrance.token` et `time.sleep` aussi : ni réseau, ni attente."""

    def lire_article(self, code_http):
        requetes, pauses = [], []

        def urlopen(requete, timeout=None):
            requetes.append(requete.full_url)
            raise urllib.error.HTTPError(requete.full_url, code_http, "simulé", {}, io.BytesIO(b""))
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=Pannes.TROUVE), \
             mock.patch.object(travaux.legifrance, "token", return_value="jeton fictif"), \
             mock.patch("urllib.request.urlopen", urlopen), \
             mock.patch("time.sleep", pauses.append), \
             mock.patch.dict(travaux.legifrance.DERNIERE_PANNE, {"quand": None, "quoi": None, "nombre": 0}):
            r = travaux.travaux_pour_article("Code de l'environnement", "L. 181-18-1", "2024-03-15")
        return r, requetes, pauses

    def test_erreur_passagere(self):
        for code_http in (503, 429):
            with self.subTest(code_http=code_http):
                r, requetes, pauses = self.lire_article(code_http)
                self.assertEqual(len(requetes), 4)
                self.assertEqual(pauses, [1.0, 2.0, 4.0])
                self.assertIn(str(code_http), r["panne"])

    def test_erreur_definitive(self):
        for code_http in (403, 400):
            with self.subTest(code_http=code_http):
                r, requetes, pauses = self.lire_article(code_http)
                self.assertEqual(len(requetes), 1)
                self.assertEqual(pauses, [])
                self.assertIn(str(code_http), r["panne"])


class DateInvalide(unittest.TestCase):
    """Une date invalide est refusée d'emblée, avec un message clair, sans être prise pour une
    panne de PISTE et sans aucun appel. `resoudre` et `_post` sont remplacés par des substituts."""

    INVALIDES = ["15/03/2024", "2024-02-30", "", None, "2024-13-01", "15 mars 2024"]

    def test_date_valide(self):
        for date in ("2024-03-15", "2024-3-15", "2024-02-29"):
            with self.subTest(date=date):
                self.assertTrue(travaux._date_valide(date))
        for date in self.INVALIDES:
            with self.subTest(date=date):
                self.assertFalse(travaux._date_valide(date))

    def test_refus_sans_appel(self):
        for article in ("L. 181-18", "R. 181-28"):
            for date in self.INVALIDES:
                with self.subTest(article=article, date=date), \
                     mock.patch.object(travaux.legifrance, "resoudre") as resoudre, \
                     mock.patch.object(travaux.legifrance, "_post") as post:
                    r = travaux.travaux_pour_article("Code de l'environnement", article, date)
                    self.assertFalse(r["trouve"])
                    self.assertTrue(r["date_invalide"])
                    self.assertNotIn("panne", r)
                    self.assertIn("AAAA-MM-JJ", r["message"])
                    resoudre.assert_not_called()
                    post.assert_not_called()

    def test_date_valide_poursuivie(self):
        with mock.patch.object(travaux.legifrance, "resoudre", return_value={"trouve": False}) as resoudre:
            r = travaux.travaux_pour_article("Code de l'environnement", "L. 181-18", "2024-3-15")
        resoudre.assert_called_once()
        self.assertNotIn("date_invalide", r)


class VersionEnCours(unittest.TestCase):
    """Une version en vigueur s'affiche « → en cours », et non « → 2999-01-01 » (L6).

    Le vrai `legifrance.resoudre`, PISTE seul simulé ; identifiants et textes fictifs."""

    def travaux(self, date_fin):
        legifrance = travaux.legifrance
        article = {"id": "LEGIARTI000000000001", "num": "L181-18", "texte": "Texte.",
                   "dateDebut": legifrance._ms("2023-03-12"), "dateFin": date_fin,
                   "lienModifications": Pannes.REPONSES["/consult/getArticle"]["article"]["lienModifications"]}
        reponses = dict(Pannes.REPONSES, **{"/search": {"results": [{"id": "LEGIARTI000000000001"}]},
                                            "/consult/getArticle": {"article": article}})
        with mock.patch.object(legifrance, "_CODES_MAP", {"code de l'environnement": "Code de l'environnement"}), \
             mock.patch.object(legifrance, "_post", lambda chemin, charge: reponses[chemin]):
            return travaux.travaux_pour_article("Code de l'environnement", "L. 181-18", "2024-03-15")

    def test_version_sans_terme(self):
        self.assertEqual(self.travaux(32472144000000)["version"], "2023-03-12 → en cours")

    def test_version_close(self):
        fin = travaux.legifrance._ms("2025-01-01")
        self.assertEqual(self.travaux(fin)["version"], "2023-03-12 → 2025-01-01")


class TextesDecodes(unittest.TestCase):
    """_clean : un alinéa par ligne, entités HTML décodées. Extraits fictifs."""

    HTML = ("<p>Rapport n&#176; 1234 de M.&nbsp;Dupont, d&#233;put&#233;, au nom de la commission&nbsp;:</p>"
            "<p>&laquo;&nbsp;L&apos;article 1er&nbsp;&raquo; &amp; suivants</p>")

    def test_entites_et_alineas(self):
        self.assertEqual(travaux._clean(self.HTML),
                         "Rapport n° 1234 de M. Dupont, député, au nom de la commission :\n"
                         "« L'article 1er » & suivants")

    def test_vide(self):
        for vide in ("", None):
            with self.subTest(html=vide):
                self.assertEqual(travaux._clean(vide), "")

    def test_travaux_et_expose_des_motifs_decodes(self):
        reponses = dict(Pannes.REPONSES)
        reponses["/consult/jorf"] = dict(reponses["/consult/jorf"], prepWork=self.HTML)
        reponses["/consult/dossierLegislatif"] = {"dossierLegislatif": {"exposeMotif": self.HTML}}
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=Pannes.TROUVE), \
             mock.patch.object(travaux.legifrance, "_post", lambda chemin, charge: reponses[chemin]):
            r = travaux.travaux_pour_article("Code de l'environnement", "L. 181-18-1", "2024-03-15")
        for champ in ("travaux_preparatoires", "expose_motif"):
            with self.subTest(champ=champ):
                self.assertIn("député", r[champ])
                self.assertNotIn("&", r[champ].replace("& suivants", ""))
                self.assertEqual(len(r[champ].splitlines()), 2)


class Demonstration(unittest.TestCase):
    """Le lancement direct (`python travaux.py`) exécute la démonstration jusqu'au bout."""

    def test_demonstration_en_fin_de_fichier(self):
        with open(travaux.__file__, encoding="utf-8") as f:
            derniere = ast.parse(f.read()).body[-1]
        self.assertIsInstance(derniere, ast.If)
        self.assertIn("__main__", ast.unparse(derniere.test))

    def test_lancement_direct(self):
        """travaux.py est exécuté comme un script, avec un faux module `legifrance` qui répond
        comme PISTE et trouve un dossier législatif : la démonstration va jusqu'à `dossier_pieces`."""
        faux = types.ModuleType("legifrance")
        faux._panne = str
        faux.alineas_de_html = travaux.legifrance.alineas_de_html     # sans réseau
        faux.resoudre = lambda code, article, date, exact=False: {
            "trouve": True, "exact": True, "id": "LEGIARTI000000000001", "num": article,
            "version_debut": "2017-03-01", "version_fin": None}
        faux._post = lambda chemin, charge: Pannes.REPONSES[chemin]
        sortie = io.StringIO()
        with mock.patch.dict(sys.modules, {"legifrance": faux}), contextlib.redirect_stdout(sortie):
            runpy.run_path(travaux.__file__, run_name="__main__")
        self.assertIn("Rapport", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
