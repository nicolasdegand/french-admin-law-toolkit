# -*- coding: utf-8 -*-
"""Tests de eurlex.py qui ne demandent pas de réseau : le point d'accès SPARQL est simulé.

Lancement, depuis la racine du dépôt :
    python -m unittest discover -s connecteurs -v
"""
import ast
import io
import json
import socket
import unittest
import urllib.error
import urllib.parse
from unittest import mock

import eurlex


def reponse_sparql(lignes):
    """Substitut de `urlopen` qui rend des résultats SPARQL : [(celex, titre, date), ...]."""
    corps = {"results": {"bindings": [
        {"celex": {"value": c}, "title": {"value": t}, "date": {"value": d}} for c, t, d in lignes]}}
    return mock.Mock(return_value=mock.Mock(read=lambda: json.dumps(corps).encode("utf-8")))


def requete_envoyee(substitut):
    """Texte de la requête SPARQL passée au substitut de `urlopen` lors de son dernier appel."""
    url = substitut.call_args[0][0].full_url
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["query"][0]


class Pannes(unittest.TestCase):
    """Une panne du point d'accès lève une erreur au lieu de rendre une liste vide."""

    QUESTION = "évaluation des incidences sur l'environnement"

    def test_reseau(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("réseau coupé")):
            with self.assertRaises(urllib.error.URLError):
                eurlex.chercher(self.QUESTION)

    def test_delai_depasse(self):
        with mock.patch("urllib.request.urlopen", side_effect=socket.timeout("délai dépassé")):
            with self.assertRaises(socket.timeout):
                eurlex.chercher(self.QUESTION)

    def test_erreur_http(self):
        erreur = urllib.error.HTTPError(eurlex.ENDPOINT, 503, "Service Unavailable", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=erreur):
            with self.assertRaises(urllib.error.HTTPError):
                eurlex.chercher(self.QUESTION)

    def test_panne_avec_acte_phare(self):
        """Même quand un acte phare est reconnu sans réseau, la panne est signalée."""
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("réseau coupé")):
            with self.assertRaises(urllib.error.URLError):
                eurlex.chercher("durée de conservation des données au regard du RGPD")


class Reponses(unittest.TestCase):
    """Quand le point d'accès répond, les résultats sont rendus comme auparavant. Titres fictifs."""

    def test_resultats(self):
        lignes = [("32011L0092", "Directive concernant l'évaluation des incidences de certains projets "
                                 "publics et privés sur l'environnement", "2011-12-13")]
        with mock.patch("urllib.request.urlopen", reponse_sparql(lignes)):
            r = eurlex.chercher("évaluation des incidences sur l'environnement")
        self.assertEqual([x["celex"] for x in r], ["32011L0092"])
        self.assertEqual(r[0]["lien"], "https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32011L0092")

    def test_aucun_resultat(self):
        with mock.patch("urllib.request.urlopen", reponse_sparql([])):
            self.assertEqual(eurlex.chercher("évaluation des incidences sur l'environnement"), [])

    def test_acte_phare_en_tete(self):
        with mock.patch("urllib.request.urlopen", reponse_sparql([])):
            r = eurlex.chercher("durée de conservation des données au regard du RGPD")
        self.assertEqual(r[0]["celex"], "32016R0679")


class TypesDeDocument(unittest.TestCase):
    """_type_celex : libellés de la page « Types de documents dans EUR-Lex » en français, au
    singulier. Numéros illustratifs."""

    ATTENDUS = {
        "32016R0679": "Règlement", "32011L0092": "Directive", "32000D0479": "Décision",
        "32014H0070": "Recommandation", "32004A0101": "Avis",
        "32004M0101": "Non-opposition à une concentration notifiée",
        "32004S0101": "Décision de portée générale CECA",
        "32004X0101": "Autre document publié au JO L (ou avant 1967)",
        "32004Y0101": "Autre document publié au JO C",
        "62019CJ0123": "Arrêt (Cour de justice)", "62019CO0123": "Ordonnance (Cour de justice)",
        "62019CC0123": "Conclusions de l'avocat général (Cour de justice)",
        "62019CS0123": "Saisie-arrêt (Cour de justice)", "62019CX0123": "Délibération (Cour de justice)",
        "62019CP0123": "Prise de position (Cour de justice)",
        "62019CN0123": "Communication : nouvelle affaire (Cour de justice)",
        "62019CA0123": "Communication : arrêt (Cour de justice)",
        "62019CB0123": "Communication : ordonnance (Cour de justice)",
        "62019TJ0123": "Arrêt (Tribunal)", "62019TO0123": "Ordonnance (Tribunal)",
        "21994A1223(01)": "Accord avec un pays tiers ou une organisation internationale",
        "41998A0101": "Accord entre États membres",
        "52021PC0206": "Document préparatoire",
        "32004Z0101": "Acte de l'Union", "62019ZZ0123": "Jurisprudence de l'Union",
        "": "Document", None: "Document", "XYZ": "Document",
    }

    def test_libelles(self):
        for celex, attendu in self.ATTENDUS.items():
            with self.subTest(celex=celex):
                self.assertEqual(eurlex._type_celex(celex), attendu)

    def test_reference_d_un_acte_phare(self):
        self.assertEqual(eurlex._phares("RGPD")[0]["reference"], "Règlement — CELEX 32016R0679")


class Sigles(unittest.TestCase):
    """Les mots substitués à un sigle figurent dans l'intitulé français des actes visés, car la
    recherche porte sur les titres. Intitulés vérifiés le 25/10/2026 (Observatoire législatif du
    Parlement européen ; AIDA, Ineris, pour la directive 2012/18/UE)."""

    INTITULES = {
        "icpe": ["Directive 2010/75/UE du Parlement européen et du Conseil relative aux émissions "
                 "industrielles (prévention et réduction intégrées de la pollution)",
                 "Directive 2012/18/UE du Parlement européen et du Conseil du 4 juillet 2012 concernant "
                 "la maîtrise des dangers liés aux accidents majeurs impliquant des substances dangereuses"],
        "oqtf": ["Directive 2008/115/CE du Parlement européen et du Conseil relative aux normes et "
                 "procédures communes applicables dans les États membres au retour des ressortissants "
                 "de pays tiers en séjour irrégulier"],
        "nis2": ["Directive (UE) 2022/2555 du Parlement européen et du Conseil concernant des mesures "
                 "destinées à assurer un niveau élevé commun de cybersécurité dans l'ensemble de l'Union"],
        "dma": ["Règlement (UE) 2022/1925 relatif aux marchés contestables et équitables dans le "
                "secteur numérique"],
    }

    def test_mots_dans_les_intitules(self):
        for sigle, intitules in self.INTITULES.items():
            texte = " ".join(intitules).lower()
            for mot in eurlex._mots(sigle):
                with self.subTest(sigle=sigle, mot=mot):
                    self.assertIn(mot, texte)

    def test_variantes_d_un_meme_acte(self):
        self.assertEqual(eurlex._mots("digital markets act"), eurlex._mots("DMA"))
        self.assertEqual(eurlex._mots("NIS 2"), eurlex._mots("NIS2"))


class Classement(unittest.TestCase):
    """Comportement décrit par la docstring de `chercher` : un titre est retenu s'il contient l'un
    des mots (OU), ceux qui n'en contiennent qu'un sont écartés dès qu'un autre en contient deux.
    Titres fictifs."""

    QUESTION = "évaluation des incidences sur l'environnement"

    def test_un_seul_mot_suffit(self):
        lignes = [("32001L0001", "Directive relative à l'environnement marin", "2001-01-01")]
        with mock.patch("urllib.request.urlopen", reponse_sparql(lignes)):
            self.assertEqual([r["celex"] for r in eurlex.chercher(self.QUESTION)], ["32001L0001"])

    def test_un_seul_mot_ecarte_si_un_titre_en_contient_deux(self):
        lignes = [("32001L0001", "Directive relative à l'environnement marin", "2001-01-01"),
                  ("32011L0092", "Directive concernant l'évaluation des incidences sur l'environnement",
                   "2011-12-13"),
                  ("32020L0002", "Directive relative à l'évaluation de la qualité de l'air", "2020-01-01")]
        with mock.patch("urllib.request.urlopen", reponse_sparql(lignes)):
            self.assertEqual([r["celex"] for r in eurlex.chercher(self.QUESTION)], ["32011L0092"])

    def test_plus_de_mots_puis_plus_recent(self):
        lignes = [("32001L0001", "Directive relative à l'évaluation des incidences", "2001-01-01"),
                  ("32020L0002", "Directive relative à l'évaluation de l'environnement", "2020-01-01"),
                  ("32011L0092", "Directive concernant l'évaluation des incidences sur l'environnement",
                   "2011-12-13")]
        with mock.patch("urllib.request.urlopen", reponse_sparql(lignes)):
            self.assertEqual([r["celex"] for r in eurlex.chercher(self.QUESTION)],
                             ["32011L0092", "32020L0002", "32001L0001"])


class ActesPhares(unittest.TestCase):
    """Chaque acte phare porte sa date. Dates vérifiées le 25/10/2026 sur EUR-Lex (intitulé de
    l'acte) ; pour le règlement 2022/1925, dont EUR-Lex refuse la lecture automatique, sur un
    document de la Chambre des représentants de Belgique (DOC 55 3813/001)."""

    DATES = {"32022R2065": "2022-10-19", "32022R1925": "2022-09-14", "32024R1689": "2024-06-13",
             "32023R2854": "2023-12-13", "32022R0868": "2022-05-30", "32022L2555": "2022-12-14",
             "32022R2554": "2022-12-14", "32016R0679": "2016-04-27", "32022L2464": "2022-12-14",
             "32014R0910": "2014-07-23"}

    def test_dates_verifiees(self):
        self.assertEqual({celex: date for _, celex, date, _ in eurlex._ACTES_PHARES}, self.DATES)

    def test_annee_de_la_date_et_du_numero_celex(self):
        for _, celex, date, _ in eurlex._ACTES_PHARES:
            with self.subTest(celex=celex):
                self.assertRegex(date, r"^\d{4}-\d{2}-\d{2}$")
                self.assertEqual(date[:4], celex[1:5])

    def test_date_rendue(self):
        with mock.patch("urllib.request.urlopen", reponse_sparql([])):
            r = eurlex.chercher("durée de conservation des données au regard du RGPD")
        self.assertEqual(r[0]["date"], "2016-04-27")


class TousLesTermes(unittest.TestCase):
    """chercher_termes : titres qui contiennent tous les termes choisis par l'appelant, par l'index
    plein texte du point d'accès. Titres fictifs."""

    def requete(self, *a, **kw):
        substitut = reponse_sparql([])
        with mock.patch("urllib.request.urlopen", substitut):
            eurlex.chercher_termes(*a, **kw)
        return requete_envoyee(substitut)

    def test_index_plein_texte_en_et(self):
        q = self.requete(["Taxe", "valeur ajoutée"])
        self.assertIn("?title bif:contains '\"Taxe\" AND \"valeur ajoutée\"' OPTION (score ?sc)", q)
        self.assertIn("ORDER BY DESC(?sc)", q)

    def test_legislation_par_defaut(self):
        self.assertIn('FILTER(STRSTARTS(STR(?celex),"3"))', self.requete(["taxe"]))
        self.assertIn('STRSTARTS(STR(?celex),"6")', self.requete(["taxe"], secteurs=("3", "6")))

    def test_resumes_ecartes_rectificatifs_demandes(self):
        q = self.requete(["taxe"])
        self.assertIn('FILTER(!CONTAINS(STR(?celex), "_SUM"))', q)
        self.assertNotIn('"R("', q)

    def celex_et_rectificatifs(self, lignes, k=6):
        with mock.patch("urllib.request.urlopen", reponse_sparql(lignes)):
            return [(x["celex"], x["rectificatifs"]) for x in eurlex.chercher_termes(["émissions"], k=k)]

    def test_rectificatifs_rattaches_a_l_acte(self):
        lignes = [("32010L0075", "Directive relative aux émissions industrielles", "2010-11-24"),
                  ("32010L0075R(03)", "Rectificatif à la directive relative aux émissions", "2012-06-19"),
                  ("32010L0075R(15)", "Rectificatif à la directive relative aux émissions", "2022-02-10"),
                  ("32024L1785", "Directive modifiant la directive relative aux émissions", "2024-04-24")]
        self.assertEqual(self.celex_et_rectificatifs(lignes),
                         [("32010L0075", ["32010L0075R(03)", "32010L0075R(15)"]), ("32024L1785", [])])

    def test_rectificatif_classe_avant_son_acte(self):
        """L'acte garde son propre rang ; le rectificatif ne prend pas de place."""
        lignes = [("32010L0075R(03)", "Rectificatif à la directive relative aux émissions", "2012-06-19"),
                  ("32024L1785", "Directive modifiant la directive relative aux émissions", "2024-04-24"),
                  ("32010L0075", "Directive relative aux émissions industrielles", "2010-11-24")]
        self.assertEqual(self.celex_et_rectificatifs(lignes),
                         [("32024L1785", []), ("32010L0075", ["32010L0075R(03)"])])

    def test_rectificatif_sans_son_acte(self):
        lignes = [("31992L0043R(08)", "Rectificatif à la directive 92/43/CEE", "2026-03-31")]
        self.assertEqual(self.celex_et_rectificatifs(lignes), [("31992L0043R(08)", [])])

    def test_k_compte_apres_rattachement(self):
        lignes = [("32010L0075", "Directive relative aux émissions", "2010-11-24"),
                  ("32010L0075R(03)", "Rectificatif à la directive relative aux émissions", "2012-06-19"),
                  ("32024L1785", "Directive modifiant la directive relative aux émissions", "2024-04-24")]
        self.assertEqual([c for c, _ in self.celex_et_rectificatifs(lignes, k=2)], ["32010L0075", "32024L1785"])

    def test_chercher_inchangee(self):
        substitut = reponse_sparql([])
        with mock.patch("urllib.request.urlopen", substitut):
            eurlex.chercher("évaluation des incidences sur l'environnement")
        q = requete_envoyee(substitut)
        self.assertNotIn("bif:contains", q)
        self.assertIn(" || ", q.split("FILTER(")[1])

    def test_expressions(self):
        attendus = {"valeur ajoutée": '"valeur ajoutée"',
                    "information en matière d'environnement": '"information en matière d environnement"',
                    "L’Union": '"L Union"', 'règlement "omnibus"': '"règlement omnibus"',
                    "a'b\\c (UE)*": '"a b c UE"', "  ": None, "'": None}
        for terme, attendu in attendus.items():
            with self.subTest(terme=terme):
                self.assertEqual(eurlex._expression_plein_texte(terme), attendu)

    def test_rien_ne_termine_la_chaine(self):
        q = self.requete(["l'accès", 'a"b', "c\\d", "e\nf"])
        expression = q.split("bif:contains '")[1].split("' OPTION")[0]
        self.assertEqual(expression, '"l accès" AND "a b" AND "c d" AND "e f"')

    def test_sans_terme_pas_de_requete(self):
        substitut = reponse_sparql([])
        with mock.patch("urllib.request.urlopen", substitut):
            for termes in ([], None, ["", "  "], "'"):
                with self.subTest(termes=termes):
                    self.assertEqual(eurlex.chercher_termes(termes), [])
        substitut.assert_not_called()

    def test_chaine_seule(self):
        """Une chaîne est prise comme un seul terme, non comme une suite de lettres."""
        self.assertIn("bif:contains '\"valeur ajoutée\"'", self.requete("valeur ajoutée"))

    def test_resultats_dans_l_ordre_du_point_d_acces(self):
        lignes = [("32006L0112", "Directive relative au système commun de taxe sur la valeur ajoutée",
                   "2006-11-28"),
                  ("32022L0542", "Directive modifiant les taux de taxe sur la valeur ajoutée", "2022-04-05"),
                  ("32008L0008", "Directive concernant le lieu des prestations de services", "2008-02-12")]
        with mock.patch("urllib.request.urlopen", reponse_sparql(lignes)):
            r = eurlex.chercher_termes(["taxe", "valeur ajoutée"], k=2)
        self.assertEqual([x["celex"] for x in r], ["32006L0112", "32022L0542"])
        self.assertEqual(set(r[0]), {"reference", "celex", "type", "titre", "date", "lien", "rectificatifs"})
        self.assertEqual(r[0]["reference"], "Directive — CELEX 32006L0112")

    def test_pas_d_acte_phare(self):
        with mock.patch("urllib.request.urlopen", reponse_sparql([])):
            self.assertEqual(eurlex.chercher_termes(["RGPD"]), [])

    def test_panne(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("réseau coupé")):
            with self.assertRaises(urllib.error.URLError):
                eurlex.chercher_termes(["taxe"])


class Structure(unittest.TestCase):
    """La démonstration (`if __name__ == "__main__":`) est la dernière instruction du fichier :
    une fonction définie après elle n'existerait pas encore quand elle s'exécute."""

    def test_demonstration_en_fin_de_fichier(self):
        with open(eurlex.__file__, encoding="utf-8") as f:
            derniere = ast.parse(f.read()).body[-1]
        self.assertIsInstance(derniere, ast.If)
        self.assertIn("__main__", ast.unparse(derniere.test))

    def test_ensembles_sans_doublon(self):
        """Un élément écrit deux fois dans un ensemble littéral ne compte qu'une fois : le doublon
        signale une faute de saisie."""
        with open(eurlex.__file__, encoding="utf-8") as f:
            arbre = ast.parse(f.read())
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Set):
                valeurs = [e.value for e in noeud.elts if isinstance(e, ast.Constant)]
                doublons = sorted({v for v in valeurs if valeurs.count(v) > 1})
                with self.subTest(ligne=noeud.lineno):
                    self.assertEqual(doublons, [])


if __name__ == "__main__":
    unittest.main()
