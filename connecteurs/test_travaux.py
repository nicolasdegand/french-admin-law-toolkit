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
    """travaux_pour_article demande l'article exact et renvoie le refus de legifrance.py.

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
        """Le vrai `legifrance.resoudre`, PISTE seul simulé : Légifrance renvoie « L181-18 »."""
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


class PlusieursTextes(unittest.TestCase):
    """Les textes qui ont produit la version sont tous renvoyés, chacun avec ses travaux, sans
    hiérarchie ; un lien de codification est écarté. PISTE simulé ; identifiants fictifs."""

    def lien(self, type_, orientation, cid, date):
        return {"linkType": type_, "linkOrientation": orientation, "textCid": cid,
                "datePubliTexte": date, "textTitle": "Texte " + cid[-2:], "natureText": "LOI"}

    def travaux(self, liens):
        def faux_post(chemin, charge):
            if chemin == "/consult/getArticle":
                return {"article": {"lienModifications": liens}}
            if chemin == "/consult/jorf":
                n = charge["textCid"][-2:]
                return {"nature": "LOI", "title": "Loi " + n, "prepWork": "<p>Travaux %s</p>" % n,
                        "dossiersLegislatifs": [{"id": "JORFDOLE0000000000" + n}]}
            if chemin == "/consult/dossierLegislatif":
                n = charge["id"][-2:]
                return {"dossierLegislatif": {"arborescence": {"niveaux": [{"libelle": "Sénat", "liens": [
                    {"libelle": "Rapport " + n, "lien": "https://exemple.invalid/rapport" + n}]}]},
                    "exposeMotif": "<p>Motifs %s</p>" % n}}
            raise AssertionError("appel inattendu : " + chemin)
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=Pannes.TROUVE), \
             mock.patch.object(travaux.legifrance, "_post", faux_post):
            return travaux.travaux_pour_article("Code de l'environnement", "L. 123-2", "2016-09-01")

    def test_un_texte_au_premier_niveau(self):
        r = self.travaux([self.lien("CODIFICATION", "source", "JORFTEXT000000000011", "2000-09-21"),
                          self.lien("MODIFICATION", "source", "JORFTEXT000000000013", "2003-07-31")])
        self.assertEqual(len(r["textes"]), 1)
        self.assertEqual(r["loi"]["cid"], "JORFTEXT000000000013")
        self.assertEqual(r["travaux_preparatoires"], "Travaux 13")
        self.assertEqual(r["expose_motif"], "Motifs 13")
        self.assertEqual(r["textes"][0]["loi"], r["loi"])
        self.assertEqual(r["ratione_temporis"], travaux._RATIONE_TEMPORIS)
        self.assertNotIn("avertissement", r)

    def test_plusieurs_textes_sans_hierarchie(self):
        r = self.travaux([self.lien("MODIFIE", "cible", "JORFTEXT000000000017", "2016-08-09"),
                          self.lien("MODIFIE", "cible", "JORFTEXT000000000016", "2016-08-05")])
        self.assertTrue(r["trouve"])
        self.assertEqual([t["loi"]["cid"] for t in r["textes"]],
                         ["JORFTEXT000000000016", "JORFTEXT000000000017"])
        self.assertEqual([t["travaux_preparatoires"] for t in r["textes"]], ["Travaux 16", "Travaux 17"])
        self.assertEqual([t["pieces"][0]["libelle"] for t in r["textes"]], ["Rapport 16", "Rapport 17"])
        for champ in ("loi", "lien_texte", "lien_dossier", "travaux_preparatoires", "pieces", "expose_motif"):
            self.assertNotIn(champ, r)
        self.assertEqual(r["avertissement"], travaux._AVERTISSEMENT_PLUSIEURS)
        self.assertEqual(r["ratione_temporis"], travaux._RATIONE_TEMPORIS_PLUSIEURS)

    def test_avertissement_propre_a_chaque_texte(self):
        liens = [self.lien("MODIFIE", "cible", "JORFTEXT000000000016", "2016-08-05"),
                 self.lien("MODIFIE", "cible", "JORFTEXT000000000017", "2016-08-09")]
        with mock.patch.object(travaux, "_avertissements",
                               lambda nature, titre: [titre] if titre == "Loi 16" else []):
            r = self.travaux(liens)
        self.assertEqual(r["textes"][0]["avertissement"], "Loi 16")
        self.assertNotIn("avertissement", r["textes"][1])

    def test_aucun_texte(self):
        r = self.travaux([])
        self.assertFalse(r["trouve"])
        self.assertEqual(r["message"], "Texte créateur de la version non identifié.")


class ArticleCodifie(unittest.TestCase):
    """Version insérée dans le code par codification : les textes sont ceux de la disposition
    codifiée, la réponse porte `codification` et un avertissement. PISTE simulé ; identifiants
    fictifs."""

    CODIF = {"linkType": "CODIFICATION", "linkOrientation": "source", "textCid": "JORFTEXT000000000011",
             "datePubliTexte": "2000-09-21", "textTitle": "Ordonnance fictive de codification",
             "natureText": "ORDONNANCE"}
    ARTICLE = {"id": "LEGIARTI000000000100", "dateDebut": 969487200000,
               "lienModifications": [CODIF],
               "lienConcordes": [{"linkType": "CONCORDE", "linkOrientation": "cible",
                                  "articleId": "LEGIARTI000000000301", "textCid": "JORFTEXT000000000042",
                                  "natureText": "LOI", "textTitle": "Loi fictive 83 - art. 1 (Ab)"}]}
    ANCIEN = {"id": "LEGIARTI000000000301", "lienModifications": []}

    def travaux(self, ancien_en_panne=False):
        def faux_post(chemin, charge):
            if chemin == "/consult/getArticle":
                if charge["id"] == "LEGIARTI000000000301":
                    if ancien_en_panne:
                        raise RuntimeError("503 Service Unavailable")
                    return {"article": self.ANCIEN}
                return {"article": self.ARTICLE}
            if chemin == "/consult/jorf":
                n = charge["textCid"][-2:]
                return {"nature": "LOI", "title": "Texte " + n, "prepWork": "<p>Travaux %s</p>" % n}
            raise AssertionError("appel inattendu : " + chemin)
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=Pannes.TROUVE), \
             mock.patch.object(travaux.legifrance, "_post", faux_post):
            return travaux.travaux_pour_article("Code de l'environnement", "L. 123-2", "2001-01-01")

    def test_disposition_d_origine(self):
        r = self.travaux()
        self.assertEqual(r["loi"]["cid"], "JORFTEXT000000000042")
        self.assertEqual(r["travaux_preparatoires"], "Travaux 42")
        self.assertEqual(r["codification"], {"codifie_par": ["Ordonnance fictive de codification"],
                                             "issu_de": ["Loi fictive 83 - art. 1 (Ab)"]})
        self.assertTrue(r["avertissement"].startswith(travaux._AVERTISSEMENT_ORIGINE))
        self.assertNotIn("panne", r)

    def test_panne_pendant_la_remontee(self):
        r = self.travaux(ancien_en_panne=True)
        self.assertTrue(r["trouve"])
        self.assertEqual(r["loi"]["cid"], "JORFTEXT000000000011")
        self.assertNotIn("codification", r)
        self.assertIn("503", r["panne"])


class DossierDuTexte(unittest.TestCase):
    """Le dossier législatif propre au texte, et non le premier rattaché ; toutes les pièces.
    Forme des réponses constatée le 02/11/2026 ; identifiants et intitulés fictifs."""

    LOI = "LOI n° 2016-9999 du 8 août 2016 pour l'exemple (1)"
    DOSSIERS = [{"id": "JORFDOLE000000000071", "titre": "Ordonnance n° 2012-9999 du 5 janvier 2012 fictive"},
                {"id": "JORFDOLE000000000072", "titre": "LOI n° 2016-9999 du 8 août 2016 pour l'exemple"},
                {"id": "JORFDOLE000000000073", "titre": "Ordonnance n° 2015-9999 du 23 septembre 2015 fictive"}]

    def test_par_numero(self):
        propre, autres = travaux._dossier_du_texte(self.DOSSIERS, self.LOI)
        self.assertEqual(propre["id"], "JORFDOLE000000000072")
        self.assertEqual([d["id"] for d in autres], ["JORFDOLE000000000071", "JORFDOLE000000000073"])

    def test_par_intitule_sans_numero(self):
        dossiers = [{"id": "JORFDOLE000000000074", "titre": "Autre texte"},
                    {"id": "JORFDOLE000000000075", "titre": "Loi relative à  l'Exemple"}]
        propre, autres = travaux._dossier_du_texte(dossiers, "LOI relative à l'exemple (1)")
        self.assertEqual(propre["id"], "JORFDOLE000000000075")
        self.assertEqual(len(autres), 1)

    def test_dossier_seul(self):
        seul = [{"id": "JORFDOLE000000000076", "titre": "Intitulé sans rapport"}]
        self.assertEqual(travaux._dossier_du_texte(seul, self.LOI), (seul[0], []))

    def test_plusieurs_sans_le_sien(self):
        propre, autres = travaux._dossier_du_texte([self.DOSSIERS[0], self.DOSSIERS[2]], self.LOI)
        self.assertIsNone(propre)
        self.assertEqual(len(autres), 2)

    def test_aucun_dossier(self):
        self.assertEqual(travaux._dossier_du_texte(None, self.LOI), (None, []))

    def pieces(self, n, max_pieces=None):
        liens = [{"libelle": "Pièce %d" % i, "lien": "https://exemple.invalid/%d" % i} for i in range(n)]
        reponse = {"dossierLegislatif": {"arborescence": {"niveaux": [{"libelle": "Sénat", "liens": liens}]}}}
        with mock.patch.object(travaux.legifrance, "_post", lambda chemin, charge: reponse):
            return travaux.dossier_pieces("JORFDOLE000000000072", max_pieces=max_pieces)

    def test_toutes_les_pieces(self):
        r = self.pieces(52)
        self.assertEqual(len(r["pieces"]), 52)
        self.assertNotIn("pieces_tronquees", r)

    def test_coupe_signalee(self):
        r = self.pieces(52, max_pieces=40)
        self.assertEqual(len(r["pieces"]), 40)
        self.assertTrue(r["pieces_tronquees"])
        self.assertEqual(r["nombre_pieces"], 52)
        self.assertNotIn("pieces_tronquees", self.pieces(30, max_pieces=40))

    def travaux(self, dossiers):
        def faux_post(chemin, charge):
            if chemin == "/consult/getArticle":
                return {"article": {"lienModifications": [
                    {"linkType": "MODIFIE", "linkOrientation": "cible", "textCid": "JORFTEXT000000000070",
                     "datePubliTexte": "2016-08-09", "textTitle": self.LOI, "natureText": "LOI"}]}}
            if chemin == "/consult/jorf":
                return {"nature": "LOI", "title": self.LOI, "prepWork": "", "dossiersLegislatifs": dossiers}
            if chemin == "/consult/dossierLegislatif":
                return {"dossierLegislatif": {"arborescence": {"niveaux": [{"libelle": "Sénat", "liens": [
                    {"libelle": "Rapport " + charge["id"][-2:], "lien": "https://exemple.invalid/" + charge["id"]}]}]}}}
            raise AssertionError("appel inattendu : " + chemin)
        with mock.patch.object(travaux.legifrance, "resoudre", return_value=Pannes.TROUVE), \
             mock.patch.object(travaux.legifrance, "_post", faux_post):
            return travaux.travaux_pour_article("Code de l'environnement", "L. 123-2", "2016-09-01")

    def test_reponse_dossier_propre(self):
        r = self.travaux(self.DOSSIERS)
        self.assertEqual(r["lien_dossier"], travaux._lien_dossier("JORFDOLE000000000072"))
        self.assertEqual([p["libelle"] for p in r["pieces"]], ["Rapport 72"])
        self.assertEqual([d["lien"] for d in r["autres_dossiers"]],
                         [travaux._lien_dossier("JORFDOLE000000000071"),
                          travaux._lien_dossier("JORFDOLE000000000073")])
        self.assertNotIn("avertissement", r)

    def test_reponse_sans_dossier_propre(self):
        r = self.travaux([self.DOSSIERS[0], self.DOSSIERS[2]])
        self.assertIsNone(r["lien_dossier"])
        self.assertEqual(r["pieces"], [])
        self.assertEqual(len(r["autres_dossiers"]), 2)
        self.assertEqual(r["avertissement"], travaux._AVERTISSEMENT_DOSSIERS)


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
        faux.textes_de_version = travaux.legifrance.textes_de_version  # sans réseau
        faux.textes_produisant = travaux.legifrance.textes_produisant  # sans réseau ici : lien CREE
        faux._fold = travaux.legifrance._fold                          # sans réseau
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
