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
from unittest import mock

import eurlex


def reponse_sparql(lignes):
    """Substitut de `urlopen` qui rend des résultats SPARQL : [(celex, titre, date), ...]."""
    corps = {"results": {"bindings": [
        {"celex": {"value": c}, "title": {"value": t}, "date": {"value": d}} for c, t, d in lignes]}}
    return mock.Mock(return_value=mock.Mock(read=lambda: json.dumps(corps).encode("utf-8")))


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


class Structure(unittest.TestCase):
    """La démonstration (`if __name__ == "__main__":`) est la dernière instruction du fichier :
    une fonction définie après elle n'existerait pas encore quand elle s'exécute."""

    def test_demonstration_en_fin_de_fichier(self):
        with open(eurlex.__file__, encoding="utf-8") as f:
            derniere = ast.parse(f.read()).body[-1]
        self.assertIsInstance(derniere, ast.If)
        self.assertIn("__main__", ast.unparse(derniere.test))


if __name__ == "__main__":
    unittest.main()
