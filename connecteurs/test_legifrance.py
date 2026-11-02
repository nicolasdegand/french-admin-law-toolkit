# -*- coding: utf-8 -*-
"""Tests de legifrance.py qui ne demandent ni réseau ni identifiants PISTE.

Lancement, depuis la racine du dépôt :
    python -m unittest discover -s connecteurs -v
"""
import ast
import re
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
        "238 quindecies": ["238 quindecies", "238quindecies"],
        "L. 54 A": ["L54 A", "L54A"],
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
    """_meme_article : la désignation demandée et le numéro renvoyé par Légifrance coïncident-ils ?"""

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
    """Substitut de `_post` : Légifrance renvoie toujours l'article `num_rendu`, quel que soit le
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


class PanneDePiste(Exception):
    """Erreur simulée : PISTE ne répond pas."""


def post_en_panne(chemin_en_panne, num_rendu="L181-18", fond=None, a_partir_de=1, versions=()):
    """Substitut de `_post` qui lève `PanneDePiste` sur `chemin_en_panne` (et, si `fond` est
    donné, seulement pour ce fonds), à partir du `a_partir_de`-ième appel à ce chemin ; les autres
    appels répondent comme `faux_post`. `versions` : versions renvoyées par getArticle."""
    normal = faux_post(num_rendu)
    compte = {"n": 0}

    def _post(chemin, charge):
        if chemin == chemin_en_panne and (fond is None or charge.get("fond") == fond):
            compte["n"] += 1
            if compte["n"] >= a_partir_de:
                raise PanneDePiste("503 Service Unavailable")
        reponse = normal(chemin, charge)
        if chemin == "/consult/getArticle" and versions:
            reponse["article"]["articleVersions"] = list(versions)
        return reponse
    return _post


class Pannes(unittest.TestCase):
    """Une panne de PISTE est signalée par le champ `panne`, et non confondue avec une absence."""

    CODE = "Code de l'environnement"
    LOI = "loi n° 78-17"

    def setUp(self):
        for patch in (mock.patch.object(legifrance, "_CODES_MAP", {"code de l'environnement": self.CODE}),
                      mock.patch.dict(legifrance._TOC_CACHE, clear=True),
                      mock.patch.dict(legifrance.DERNIERE_PANNE, {"quand": None, "quoi": None, "nombre": 0})):
            patch.start()
            self.addCleanup(patch.stop)

    def appeler(self, faux, fonction, *args, **kwargs):
        with mock.patch.object(legifrance, "_post", faux):
            return fonction(*args, **kwargs)

    def test_loi_non_identifiee_panne(self):
        r = self.appeler(post_en_panne("/search", fond="LODA_DATE"),
                         legifrance.resoudre_loi, self.LOI, "article 6", "2024-03-15")
        self.assertFalse(r["trouve"])
        self.assertIn("503", r["panne"])

    def test_loi_plan_panne(self):
        r = self.appeler(post_en_panne("/consult/legiPart"),
                         legifrance.resoudre_loi, self.LOI, "article 6", "2024-03-15")
        self.assertFalse(r["trouve"])
        self.assertIn("503", r["panne"])

    def test_loi_absente_sans_panne(self):
        def sans_resultat(chemin, charge):
            return {"results": []}
        r = self.appeler(sans_resultat, legifrance.resoudre_loi, self.LOI, "article 6", "2024-03-15")
        self.assertFalse(r["trouve"])
        self.assertNotIn("panne", r)

    def test_historique_loi_panne(self):
        h = self.appeler(post_en_panne("/search", fond="LODA_DATE"),
                         legifrance.historique_article, self.LOI, "article 6", "2024-03-15")
        self.assertFalse(h["trouve"])
        self.assertIn("503", h["panne"])

    def test_historique_article_panne(self):
        # 1er getArticle : dans `resoudre` ; 2e : dans `historique_article`, en panne
        h = self.appeler(post_en_panne("/consult/getArticle", num_rendu="L181-18", a_partir_de=2),
                         legifrance.historique_article, self.CODE, "L. 181-18", "2024-03-15")
        self.assertEqual(h, {"trouve": False, "panne": "503 Service Unavailable"})

    def test_historique_version_panne(self):
        # 3e getArticle, celui de la version, en panne : l'historique est renvoyé, avec `panne`
        version = {"id": "LEGIARTI000000000004", "version": "1.0", "dateDebut": None, "dateFin": None}
        h = self.appeler(post_en_panne("/consult/getArticle", num_rendu="L181-18", a_partir_de=3,
                                       versions=[version]),
                         legifrance.historique_article, self.CODE, "L. 181-18", "2024-03-15")
        self.assertTrue(h["trouve"])
        self.assertIn("503", h["panne"])
        self.assertIsNone(h["versions"][0]["modif"])

    def test_historique_sans_panne(self):
        h = self.appeler(faux_post("L181-18"), legifrance.historique_article,
                         self.CODE, "L. 181-18", "2024-03-15")
        self.assertTrue(h["trouve"])
        self.assertNotIn("panne", h)

    def test_subdivision_de_code_panne(self):
        r = self.appeler(post_en_panne("/search"), legifrance.resoudre_subdivision,
                         "code", self.CODE, [("titre", "Ier")], "2024-03-15")
        self.assertFalse(r["trouve"])
        self.assertIn("503", r["panne"])

    def test_compteur_de_pannes(self):
        for _ in range(2):
            self.appeler(post_en_panne("/consult/legiPart"),
                         legifrance.resoudre_loi, self.LOI, "article 6", "2024-03-15")
        self.assertEqual(legifrance.DERNIERE_PANNE["nombre"], 2)


class DateDeFin(unittest.TestCase):
    """_iso_fin : la date conventionnelle du 1er janvier 2999 (et au-delà) veut dire « pas de fin »."""

    def test_date_sans_terme(self):
        for date in ("2999-01-01", "2999-12-31", "3000-01-01"):
            with self.subTest(date=date):
                self.assertIsNone(legifrance._iso_fin(legifrance._ms(date)))
        self.assertEqual(legifrance._ms("2999-01-01"), 32472144000000)

    def test_vraies_dates_conservees(self):
        for date in ("2027-01-01", "2023-03-12", "2998-12-31"):
            with self.subTest(date=date):
                self.assertEqual(legifrance._iso_fin(legifrance._ms(date)), date)

    def test_date_absente(self):
        self.assertIsNone(legifrance._iso_fin(None))

    def test_resoudre_version_en_vigueur(self):
        def faux_post(chemin, charge):
            if chemin == "/search":
                return {"results": [{"id": "LEGIARTI000000000001"}]}
            return {"article": {"id": charge["id"], "num": "L181-18", "texte": "Texte.",
                                "dateDebut": legifrance._ms("2023-03-12"), "dateFin": 32472144000000}}
        with mock.patch.object(legifrance, "_CODES_MAP", {"code de l'environnement": "Code de l'environnement"}), \
             mock.patch.object(legifrance, "_post", faux_post):
            r = legifrance.resoudre("Code de l'environnement", "L. 181-18", "2024-03-15")
        self.assertEqual(r["version_debut"], "2023-03-12")
        self.assertIsNone(r["version_fin"])


class ConversionDesDates(unittest.TestCase):
    """_iso : millisecondes -> date, sans `utcfromtimestamp` (obsolète) ni limite de plateforme."""

    def test_dates(self):
        for date in ("2024-03-15", "1970-01-02", "1804-03-21", "2999-01-01"):
            with self.subTest(date=date):
                self.assertEqual(legifrance._iso(legifrance._ms(date)), date)

    def test_date_absente(self):
        self.assertIsNone(legifrance._iso(None))

    def test_sans_avertissement_d_obsolescence(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            legifrance._iso(legifrance._ms("2024-03-15"))


class TermesDeRecherche(unittest.TestCase):
    """chercher_termes envoie à Légifrance les termes séparés par des espaces, qu'ils soient
    donnés en liste ou en une seule chaîne (forme de l'exemple du README)."""

    def valeur_envoyee(self, termes):
        charges = []
        with mock.patch.object(legifrance, "_post", lambda chemin, charge: charges.append(charge) or {}):
            legifrance.chercher_termes(termes)
        return charges[0]["recherche"]["champs"][0]["criteres"][0]["valeur"] if charges else None

    def test_chaine(self):
        self.assertEqual(self.valeur_envoyee("obligation de motivation refus protection fonctionnelle"),
                         "obligation de motivation refus protection fonctionnelle")

    def test_liste(self):
        self.assertEqual(self.valeur_envoyee(["obligation de motivation", "protection fonctionnelle"]),
                         "obligation de motivation protection fonctionnelle")

    def test_sans_terme_pas_de_requete(self):
        for termes in ("", "   ", [], None):
            with self.subTest(termes=termes):
                self.assertIsNone(self.valeur_envoyee(termes))


class Subdivisions(unittest.TestCase):
    """Mentions de subdivision retirées du numéro et rendues dans `subdivision` ; fin ambiguë
    (« V ») essayée d'abord comme lettre du numéro (CGI 150 V), puis comme paragraphe."""

    def test_retirees(self):
        cas = {"article L. 181-18, I": "I", "L. 181-18 (II)": "II", "L. 181-18 al. 2": "al. 2",
               "L. 181-18, alinéa 3": "alinéa 3", "L. 181-18, premier alinéa": "premier alinéa",
               "L. 181-18, I, al. 2": "I, al. 2", "les articles L. 181-18": None}
        for article, subdivision in cas.items():
            with self.subTest(article=article):
                self.assertEqual(legifrance._art_candidates(article)[0], "L181-18")
                self.assertTrue(legifrance._meme_article(article, "L181-18"))
                self.assertEqual(legifrance._candidats_detail(article)[1], subdivision)

    def test_lettres_gardees(self):
        self.assertEqual(legifrance._art_candidates("L. 54 A")[0], "L54 A")
        self.assertEqual(legifrance._art_candidates("150 VB"), ["150 VB", "150VB"])
        self.assertEqual(legifrance._art_candidates("1649 quater A")[0], "1649 quater A")

    def test_fin_ambigue(self):
        # Le numéro tel qu'il est écrit d'abord, puis sans la fin ambiguë, avant toute cascade.
        self.assertEqual(legifrance._art_candidates("150 V"), ["150 V", "150V", "150"])
        self.assertEqual(legifrance._art_candidates("L. 181-18 V"),
                         ["L181-18 V", "L181-18V", "L181-18", "L181"])
        self.assertEqual(legifrance._candidats_detail("L. 181-18 V, al. 2")[0][2], ("L181-18", "V"))
        self.assertTrue(legifrance._meme_article("150 V", "150 V"))
        self.assertTrue(legifrance._meme_article("L. 181-18 V", "L181-18"))
        self.assertFalse(legifrance._meme_article("L. 181-18 V", "L181-19"))

    def resoudre(self, article, existants):
        """`resoudre` avec un Légifrance simulé qui ne connaît que les numéros `existants`."""
        def _post(chemin, charge):
            if chemin == "/search":
                num = charge["recherche"]["champs"][0]["criteres"][0]["valeur"]
                return {"results": [{"id": "LEGIARTI000000000001"}]} if num in existants else {"results": []}
            if chemin == "/consult/getArticle":
                return {"article": {"id": "LEGIARTI000000000001", "num": self.rendu, "texte": "Texte."}}
            raise AssertionError("appel inattendu : " + chemin)
        self.rendu = existants[0]
        with mock.patch.object(legifrance, "_CODES_MAP", {"code de l'environnement": "Code de l'environnement"}), \
             mock.patch.object(legifrance, "_post", _post):
            return legifrance.resoudre("Code de l'environnement", article, "2024-01-01", exact=True)

    def test_subdivision_rendue(self):
        r = self.resoudre("L. 181-18, I, al. 2", ["L181-18"])
        self.assertTrue(r["trouve"])
        self.assertEqual(r["subdivision"], "I, al. 2")
        self.assertNotIn("subdivision", self.resoudre("L. 181-18", ["L181-18"]))

    def test_fin_ambigue_lettre_du_numero(self):
        r = self.resoudre("150 V", ["150 V"])
        self.assertEqual((r["trouve"], r["num"]), (True, "150 V"))
        self.assertNotIn("subdivision", r)

    def test_fin_ambigue_paragraphe(self):
        r = self.resoudre("L. 181-18 V, al. 2", ["L181-18"])
        self.assertEqual((r["trouve"], r["exact"], r["num"]), (True, True, "L181-18"))
        self.assertEqual(r["subdivision"], "V, al. 2")


class Designations(unittest.TestCase):
    """_designations : lecture d'une désignation d'un ou plusieurs articles."""

    def test_listes_et_plages(self):
        cas = {
            "articles L. 181-18 et L. 181-19": [("article", "L. 181-18"), ("article", "L. 181-19")],
            "L. 181-18, L. 181-19 et L. 181-21": [("article", "L. 181-18"), ("article", "L. 181-19"),
                                                  ("article", "L. 181-21")],
            "L. 181-18 à L. 181-20": [("plage", "L. 181-18", "L. 181-20")],
            "L. 181-18 et 181-19": [("article", "L. 181-18"), ("article", "L. 181-19")],
            "R. 181-28 à 181-30": [("plage", "R. 181-28", "R. 181-30")],
            "L. 181-18, I et L. 181-19, al. 2": [("article", "L. 181-18, I"), ("article", "L. 181-19, al. 2")],
            "L. 181-18, 3° et L. 181-19": [("article", "L. 181-18, 3°"), ("article", "L. 181-19")],
            "articles 1240 et 1241": [("article", "1240"), ("article", "1241")],
            "articles 6, 7 et 8": [("article", "6"), ("article", "7"), ("article", "8")],
            "L. 314-11 8°": [("article", "L. 314-11 8°")],
        }
        for texte, attendu in cas.items():
            with self.subTest(texte=texte):
                self.assertEqual(legifrance._designations(texte), (attendu, None))

    def test_et_suivants_refuse(self):
        for texte in ("L. 181-18 et suivants", "L. 181-18 et s.", "L. 181-18 et suiv.", "L. 181-18 ss."):
            with self.subTest(texte=texte):
                elements, refus = legifrance._designations(texte)
                self.assertEqual(elements, [])
                self.assertIn("et suivants", refus)

    def test_plusieurs(self):
        self.assertTrue(legifrance._plusieurs("L. 181-18 et L. 181-19"))
        self.assertTrue(legifrance._plusieurs("L. 181-18 à L. 181-20"))
        self.assertTrue(legifrance._plusieurs("L. 181-18 et suivants"))
        for seul in ("L. 181-18", "article L. 181-18, I", "L. 54 A", "L. 314-11 8°"):
            with self.subTest(seul=seul):
                self.assertFalse(legifrance._plusieurs(seul))

    def test_resoudre_refuse_sans_appel(self):
        def interdit(chemin, charge):
            raise AssertionError("appel inattendu : " + chemin)
        with mock.patch.object(legifrance, "_post", interdit):
            for code in ("Code de l'environnement", "loi n° 78-17"):
                with self.subTest(code=code):
                    r = legifrance.resoudre(code, "articles L. 181-18 et L. 181-19", "2024-01-01")
                    self.assertFalse(r["trouve"])
                    self.assertTrue(r["plusieurs"])
                    self.assertIn("resoudre_plusieurs", r["message"])


class NumerosDuPlan(unittest.TestCase):
    """_numeros_du_plan : ordre du texte d'après `intOrdre`, articles abrogés et doublons écartés.
    Forme du plan de la loi n° 78-17 constatée le 02/11/2026 ; rangs fictifs."""

    def test_ordre_doublons_abroges(self):
        plan = {"sections": [
            {"title": "Titre II", "intOrdre": 20, "articles": [{"num": "8", "intOrdre": 1, "etat": "VIGUEUR"}]},
            {"title": "Titre Ier", "intOrdre": 10, "articles": [
                {"num": "5", "intOrdre": 5, "etat": "VIGUEUR"},
                {"num": "7", "intOrdre": 7, "etat": "VIGUEUR"},
                {"num": "5-1", "intOrdre": 6, "etat": "ABROGE"},
                {"num": "6", "intOrdre": 6, "etat": "VIGUEUR"},
                {"num": "7", "intOrdre": 8, "etat": "VIGUEUR"}]}]}
        self.assertEqual(legifrance._numeros_du_plan(plan, []), ["5", "6", "7", "8"])

    def test_sans_rang(self):
        plan = {"articles": [{"num": "1"}], "sections": [{"articles": [{"num": "2"}]}]}
        self.assertEqual(legifrance._numeros_du_plan(plan, []), ["1", "2"])


class ResoudrePlusieurs(unittest.TestCase):
    """resoudre_plusieurs : listes, plages développées avec le plan, refus. PISTE simulé ;
    identifiants fictifs."""

    PLAN = {"sections": [{"intOrdre": 1, "articles": [
        {"num": n, "intOrdre": i, "etat": "VIGUEUR"} for i, n in enumerate(
            ["L181-17", "L181-18", "L181-19", "L181-20", "L181-21"])]}]}

    def appeler(self, designation):
        def resoudre(code, num, date, exact=False):
            return {"trouve": True, "exact": True, "num": re.sub(r"[\s.]", "", num)}
        with mock.patch.object(legifrance, "_legitext_code", return_value="LEGITEXT000000000090"), \
             mock.patch.object(legifrance, "_post", lambda chemin, charge: self.PLAN), \
             mock.patch.dict(legifrance._TOC_CACHE, clear=True), \
             mock.patch.object(legifrance, "resoudre", resoudre):
            return legifrance.resoudre_plusieurs("Code de l'environnement", designation, "2024-01-01")

    def nums(self, r):
        return [a["num"] for a in r["articles"]]

    def test_liste(self):
        r = self.appeler("articles L. 181-18 et L. 181-21")
        self.assertTrue(r["trouve"])
        self.assertEqual(self.nums(r), ["L181-18", "L181-21"])

    def test_plage(self):
        self.assertEqual(self.nums(self.appeler("L. 181-18 à L. 181-20")), ["L181-18", "L181-19", "L181-20"])

    def test_subdivision_transmise(self):
        # La mention de subdivision reste attachée à son article, que `resoudre` rend ensuite.
        self.assertEqual(self.nums(self.appeler("L. 181-18, I et L. 181-21")), ["L181-18,I", "L181-21"])

    def test_plage_et_article(self):
        self.assertEqual(self.nums(self.appeler("L. 181-17 et L. 181-19 à 181-21")),
                         ["L181-17", "L181-19", "L181-20", "L181-21"])

    def test_plage_hors_vigueur(self):
        r = self.appeler("L. 181-18 à L. 181-25")
        self.assertFalse(r["trouve"])
        self.assertIn("L. 181-25 n'est pas en vigueur", r["message"])

    def test_plage_a_l_envers(self):
        self.assertIn("suit le dernier", self.appeler("L. 181-20 à L. 181-18")["message"])

    def test_et_suivants(self):
        r = self.appeler("L. 181-18 et suivants")
        self.assertEqual(r["articles"], [])
        self.assertIn("et suivants", r["message"])

    def test_plage_trop_longue(self):
        with mock.patch.object(legifrance, "_PLAGE_MAX", 2):
            self.assertIn("plus de 2 articles", self.appeler("L. 181-18 à L. 181-20")["message"])


class Structure(unittest.TestCase):
    """La démonstration (`if __name__ == "__main__":`) est la dernière instruction du fichier :
    une fonction définie après elle n'existerait pas encore quand elle s'exécute."""

    def test_demonstration_en_fin_de_fichier(self):
        with open(legifrance.__file__, encoding="utf-8") as f:
            derniere = ast.parse(f.read()).body[-1]
        self.assertIsInstance(derniere, ast.If)
        self.assertIn("__main__", ast.unparse(derniere.test))


if __name__ == "__main__":
    unittest.main()
