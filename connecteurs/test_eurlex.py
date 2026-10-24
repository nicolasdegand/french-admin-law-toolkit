# -*- coding: utf-8 -*-
"""Tests de eurlex.py qui ne demandent pas de réseau : le point d'accès SPARQL est simulé.

Lancement, depuis la racine du dépôt :
    python -m unittest discover -s connecteurs -v
"""
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


if __name__ == "__main__":
    unittest.main()
