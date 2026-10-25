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


def requete_envoyee(substitut, n=0):
    """Texte de la requête SPARQL passée au substitut de `urlopen` lors de son appel n° `n`
    (0 : la recherche ; 1 : l'état des actes trouvés)."""
    url = substitut.call_args_list[n][0][0].full_url
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


def aiguillage(actes=(), arrets=(), vigueur=(), cites=()):
    """Substitut de `urlopen` qui répond selon la requête : titres de législation (`actes`), de
    jurisprudence (`arrets`), vigueur des actes ({celex: "1" ou "0"}), acte cité dans la question
    (`cites`) ; liste vide pour la requête d'état."""
    def lignes(rangs):
        return [{"celex": {"value": c}, "title": {"value": t}, "date": {"value": d}} for c, t, d in rangs]
    def ouvrir(req, timeout=None):
        q = urllib.parse.unquote_plus(req.full_url)
        if "act_consolidated" in q:
            liaisons = []
        elif "resource_legal_in-force ?v\n}" in q:
            liaisons = [{"bc": {"value": c}, "v": {"value": v}} for c, v in dict(vigueur).items()]
        elif "VALUES ?celex" in q:
            liaisons = lignes(cites)
        elif 'STRSTARTS(STR(?celex), "6")' in q:
            liaisons = lignes(arrets)
        else:
            liaisons = lignes(actes)
        return mock.Mock(read=lambda: json.dumps({"results": {"bindings": liaisons}}).encode("utf-8"))
    return mock.Mock(side_effect=ouvrir)


class Classement(unittest.TestCase):
    """chercher : candidats de l'index plein texte (au moins deux mots de la question), classés par
    `_classer`, actes puis jurisprudence. Titres fictifs."""

    QUESTION = "chasse et conservation des oiseaux sauvages"

    def chercher(self, question=QUESTION, **kw):
        substitut = aiguillage(**kw)
        with mock.patch("urllib.request.urlopen", substitut):
            return [r["celex"] for r in eurlex.chercher(question, etat=False)], substitut

    def test_formes(self):
        self.assertEqual(eurlex._formes("animaux"), ["animal", "animau", "animaux"])
        self.assertEqual(eurlex._formes("déchet"), ["déchet", "déchets"])
        self.assertEqual(eurlex._formes("national"), ["national", "nationals", "nationaux"])

    def test_expression_paires(self):
        e = eurlex._expression_paires(["conservation", "sauvages", "chasse"])
        self.assertEqual(e, '(("conservation" OR "conservations") AND ("sauvage" OR "sauvages")) OR '
                            '(("conservation" OR "conservations") AND ("chasse" OR "chasses")) OR '
                            '(("sauvage" OR "sauvages") AND ("chasse" OR "chasses"))')
        self.assertEqual(eurlex._expression_paires(["déchets"]), '("déchet" OR "déchets")')

    def test_requete(self):
        _, substitut = self.chercher()
        q = requete_envoyee(substitut)
        self.assertIn("?title bif:contains '((\"", q)
        self.assertIn('FILTER(STRSTARTS(STR(?celex), "3"))', q)
        for d in ("R(", "_SUM", "_RES", "_INF"):
            self.assertIn(f'!CONTAINS(STR(?celex), "{d}")', q)

    def test_nombre_de_mots_puis_vigueur(self):
        actes = [("31979L0409", "Directive concernant la conservation des oiseaux sauvages", "1979-04-02"),
                 ("32009L0147", "Directive concernant la conservation des oiseaux sauvages (version codifiée)", "2009-11-30"),
                 ("32005D0734", "Décision relative aux oiseaux sauvages", "2005-10-19")]
        celex, _ = self.chercher(actes=actes, vigueur={"31979L0409": "0", "32009L0147": "1"})
        self.assertEqual(celex, ["32009L0147", "31979L0409", "32005D0734"])

    def test_type_puis_longueur(self):
        actes = [("32010D0001", "Décision sur la conservation des oiseaux", "2010-01-01"),
                 ("32010L0002", "Directive modifiant la directive sur la conservation des oiseaux", "2010-01-01"),
                 ("32010L0003", "Directive sur la conservation des oiseaux", "2010-01-01"),
                 ("32010R0004", "Projet de règlement sur la conservation des oiseaux", "2010-01-01")]
        celex, _ = self.chercher(actes=actes)
        self.assertEqual(celex, ["32010L0003", "32010L0002", "32010D0001", "32010R0004"])

    def test_actes_puis_jurisprudence(self):
        actes = [("32009L0147", "Directive concernant la conservation des oiseaux sauvages", "2009-11-30")]
        arrets = [("62003CA0079", "Affaire C-79/03 : arrêt (communication) oiseaux sauvages chasse", "2005-01-01"),
                  ("62003CJ0079", "Arrêt de la Cour, Commission contre Espagne, chasse des oiseaux sauvages", "2004-12-09")]
        celex, _ = self.chercher(actes=actes, arrets=arrets)
        self.assertEqual(celex, ["32009L0147", "62003CJ0079", "62003CA0079"])

    def test_legislation_seule(self):
        actes = [("32009L0147", "Directive concernant la conservation des oiseaux sauvages", "2009-11-30")]
        substitut = aiguillage(actes=actes, arrets=[("62003CJ0079", "Arrêt chasse oiseaux", "2004-12-09")])
        with mock.patch("urllib.request.urlopen", substitut):
            r = eurlex.chercher(self.QUESTION, secteurs=("3",), etat=False)
        self.assertEqual([x["celex"] for x in r], ["32009L0147"])

    def test_k_par_secteur(self):
        actes = [(f"3201{i}L000{i}", "Directive conservation oiseaux", "2010-01-01") for i in range(5)]
        arrets = [(f"6201{i}CJ000{i}", "Arrêt conservation oiseaux", "2010-01-01") for i in range(5)]
        substitut = aiguillage(actes=actes, arrets=arrets)
        with mock.patch("urllib.request.urlopen", substitut):
            r = eurlex.chercher(self.QUESTION, k=2, etat=False)
        self.assertEqual([x["celex"][0] for x in r], ["3", "3", "6", "6"])

    def test_acte_cite_dans_la_question(self):
        actes = [("32009L0147", "Directive concernant la conservation des oiseaux sauvages", "2009-11-30")]
        cites = [("31992L0043", "Directive 92/43/CEE concernant la conservation des habitats naturels", "1992-05-21")]
        celex, _ = self.chercher("conservation des oiseaux sauvages au regard de la directive 92/43/CEE",
                                 actes=actes, cites=cites)
        self.assertEqual(celex[0], "31992L0043")
        self.assertIn("32009L0147", celex)

    def test_actes_phares_en_tete_sans_doublon(self):
        actes = [("32016R0679", "Règlement relatif à la protection des données à caractère personnel", "2016-04-27"),
                 ("32018R1725", "Règlement relatif à la protection des données par les institutions", "2018-10-23")]
        celex, _ = self.chercher("durée de conservation des données au regard du RGPD", actes=actes)
        self.assertEqual(celex, ["32016R0679", "32018R1725"])

    def test_vigueur_demandee_pour_la_legislation_seulement(self):
        actes = [("32009L0147", "Directive concernant la conservation des oiseaux sauvages", "2009-11-30")]
        _, substitut = self.chercher(actes=actes, arrets=[("62003CJ0079", "Arrêt chasse oiseaux", "2004-12-09")])
        vig = [c for c in substitut.call_args_list if "resource_legal_in-force ?v\n}" in urllib.parse.unquote_plus(c[0][0].full_url)]
        self.assertEqual(len(vig), 1)


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

    def test_chercher_ne_cherche_pas_d_expression_exacte(self):
        """chercher demande des paires de mots, non les expressions exactes de chercher_termes."""
        substitut = reponse_sparql([])
        with mock.patch("urllib.request.urlopen", substitut):
            eurlex.chercher("évaluation des incidences sur l'environnement")
        self.assertIn(" AND ", requete_envoyee(substitut).split("bif:contains '")[1].split("'")[0])

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
        self.assertEqual(set(r[0]), {"reference", "celex", "type", "titre", "date", "lien", "rectificatifs",
                                     "en_vigueur", "fin_de_validite", "version_consolidee"})
        self.assertEqual(r[0]["reference"], "Directive — CELEX 32006L0112")

    def test_pas_d_acte_phare(self):
        with mock.patch("urllib.request.urlopen", reponse_sparql([])):
            self.assertEqual(eurlex.chercher_termes(["RGPD"]), [])

    def test_panne(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("réseau coupé")):
            with self.assertRaises(urllib.error.URLError):
                eurlex.chercher_termes(["taxe"])


def reponses(recherche, etat):
    """Substitut de `urlopen` : la requête d'état des actes reçoit `etat` (liste de dictionnaires
    de liaisons SPARQL), toute autre requête les résultats de recherche `recherche`."""
    def ouvrir(req, timeout=None):
        if "act_consolidated" in urllib.parse.unquote_plus(req.full_url):
            corps = {"results": {"bindings": [{k: {"value": v} for k, v in b.items()} for b in etat]}}
        else:
            corps = {"results": {"bindings": [
                {"celex": {"value": c}, "title": {"value": t}, "date": {"value": d}} for c, t, d in recherche]}}
        return mock.Mock(read=lambda: json.dumps(corps).encode("utf-8"))
    return mock.Mock(side_effect=ouvrir)


ETAT_2010_75 = [
    {"bc": "32010L0075", "genre": "etat", "v": "1", "d": "9999-12-31"},
    {"bc": "32010L0075", "genre": "consolidee", "c": "02010L0075-20110106"},
    {"bc": "32010L0075", "genre": "consolidee", "c": "02010L0075-20240804"},
    {"bc": "32010L0075", "genre": "consolidee", "c": "02001L0080-20160101"},   # acte abrogé par 2010/75
    {"bc": "32010L0075", "genre": "rectificatif", "c": "32010L0075R(15)"},
    {"bc": "32010L0075", "genre": "rectificatif", "c": "32010L0075R(01)"},
    {"bc": "32001L0080", "genre": "etat", "v": "0", "d": "2015-12-31"},
]


class EtatDesActes(unittest.TestCase):
    """etat_des_actes et le paramètre `etat` des deux recherches. Liaisons inspirées de Cellar
    (25/10/2026)."""

    def etats(self, celex, liaisons=ETAT_2010_75):
        substitut = reponses([], liaisons)
        with mock.patch("urllib.request.urlopen", substitut):
            return eurlex.etat_des_actes(celex), substitut

    def test_acte_en_vigueur(self):
        e, _ = self.etats(["32010L0075"])
        self.assertEqual(e["32010L0075"], {
            "en_vigueur": True, "fin_de_validite": None,
            "version_consolidee": {"celex": "02010L0075-20240804", "date": "2024-08-04",
                                   "lien": "https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:02010L0075-20240804"},
            "rectificatifs": ["32010L0075R(01)", "32010L0075R(15)"]})

    def test_acte_abroge(self):
        e, _ = self.etats(["32001L0080"])
        self.assertEqual((e["32001L0080"]["en_vigueur"], e["32001L0080"]["fin_de_validite"]), (False, "2015-12-31"))

    def test_consolidations_d_autres_actes_ignorees(self):
        e, _ = self.etats(["32010L0075"])
        self.assertTrue(e["32010L0075"]["version_consolidee"]["celex"].startswith("02010L0075-"))

    def test_acte_sans_information(self):
        e, _ = self.etats(["62019CJ0123"])
        self.assertEqual(e["62019CJ0123"], {"en_vigueur": None, "fin_de_validite": None,
                                            "version_consolidee": None, "rectificatifs": []})

    def test_une_seule_requete(self):
        _, substitut = self.etats(["32010L0075", "32001L0080", "32010L0075"])
        self.assertEqual(substitut.call_count, 1)
        x = "^^<http://www.w3.org/2001/XMLSchema#string>"
        self.assertIn(f'VALUES ?bc {{ "32010L0075"{x} "32001L0080"{x} }}', requete_envoyee(substitut))

    def test_numero_invalide_ecarte(self):
        e, substitut = self.etats(['32010L0075") || ("x', ""])
        self.assertEqual(e, {})
        substitut.assert_not_called()

    def test_chercher_termes_avec_etat(self):
        lignes = [("32010L0075", "Directive relative aux émissions industrielles", "2010-11-24"),
                  ("32010L0075R(03)", "Rectificatif à la directive relative aux émissions", "2012-06-19")]
        substitut = reponses(lignes, ETAT_2010_75)
        with mock.patch("urllib.request.urlopen", substitut):
            r = eurlex.chercher_termes(["émissions industrielles"])
        self.assertEqual(substitut.call_count, 2)
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["en_vigueur"])
        self.assertEqual(r[0]["version_consolidee"]["celex"], "02010L0075-20240804")
        self.assertEqual(r[0]["rectificatifs"], ["32010L0075R(01)", "32010L0075R(03)", "32010L0075R(15)"])

    def test_sans_etat_une_seule_requete(self):
        lignes = [("32010L0075", "Directive relative aux émissions industrielles", "2010-11-24")]
        substitut = reponses(lignes, ETAT_2010_75)
        with mock.patch("urllib.request.urlopen", substitut):
            r = eurlex.chercher_termes(["émissions industrielles"], etat=False)
        self.assertEqual(substitut.call_count, 1)
        self.assertNotIn("en_vigueur", r[0])

    def test_chercher_actes_phares_avec_etat(self):
        liaisons = [{"bc": "32016R0679", "genre": "etat", "v": "1", "d": "9999-12-31"}]
        with mock.patch("urllib.request.urlopen", reponses([], liaisons)):
            r = eurlex.chercher("durée de conservation des données au regard du RGPD")
        self.assertEqual((r[0]["celex"], r[0]["en_vigueur"]), ("32016R0679", True))

    def test_aucun_resultat_pas_de_requete_d_etat(self):
        substitut = reponses([], ETAT_2010_75)
        with mock.patch("urllib.request.urlopen", substitut):
            self.assertEqual(eurlex.chercher_termes(["introuvable"]), [])
        self.assertEqual(substitut.call_count, 1)

    def test_panne_de_la_requete_d_etat(self):
        lignes = [("32010L0075", "Directive relative aux émissions industrielles", "2010-11-24")]
        normal = reponses(lignes, [])
        def ouvrir(req, timeout=None):
            if "act_consolidated" in urllib.parse.unquote_plus(req.full_url):
                raise urllib.error.URLError("réseau coupé")
            return normal(req, timeout)
        with mock.patch("urllib.request.urlopen", side_effect=ouvrir):
            with self.assertRaises(urllib.error.URLError):
                eurlex.chercher_termes(["émissions industrielles"])


class LectureDesReferences(unittest.TestCase):
    """_lire_reference : numéro CELEX déduit de la référence telle qu'on l'écrit."""

    ACTES = {
        "directive 2011/92/UE": "32011L0092",
        "Règlement (UE) 2016/679": "32016R0679",
        "règlement (UE) n° 910/2014": "32014R0910",
        "règlement (CE) n° 1013/2006": "32006R1013",
        "règlement (CE) n° 2201/2003": "32003R2201",          # numéro de quatre chiffres > 2015
        "règlement (CEE) n° 1408/71": "31971R1408",           # année sur deux chiffres
        "règlement d'exécution (UE) 2017/2384": "32017R2384",
        "directive 92/43/CEE": "31992L0043",
        "Directive (UE) 2022/2555": "32022L2555",
        "décision n° 1386/2013/UE": "32013D1386",              # décision numérotée « n° »
        "décision 2000/532/CE": "32000D0532",
        "décision-cadre 2002/584/JAI": "32002F0584",
        "recommandation 2003/47/CE": "32003H0047",
    }

    def test_actes(self):
        for reference, celex in self.ACTES.items():
            with self.subTest(reference=reference):
                genre, candidats, _ = eurlex._lire_reference(reference)
                self.assertEqual((genre, candidats[0]), ("acte", celex))

    def test_autres_types_cherches(self):
        _, candidats, attendu = eurlex._lire_reference("directive 2016/679")
        self.assertEqual(candidats, ["32016L0679", "32016R0679", "32016D0679"])
        self.assertEqual(attendu, (2016, 679))

    def test_affaires(self):
        self.assertEqual(eurlex._lire_reference("C-461/17")[:2],
                         ("affaire", ["62017CJ0461", "62017CC0461", "62017CO0461"]))
        self.assertEqual(eurlex._lire_reference("aff. C‑6/64")[1][0], "61964CJ0006")   # trait d'union insécable
        self.assertEqual(eurlex._lire_reference("T-201/04")[1], ["62004TJ0201", "62004TO0201"])

    def test_celex(self):
        for celex in ("32016R0679", "32011D0517(01)", "02010L0075-20240804", "62017CJ0461"):
            with self.subTest(celex=celex):
                self.assertEqual(eurlex._lire_reference(celex)[:2], ("celex", [celex]))

    def test_non_reconnues(self):
        for reference in ("", None, "directive", "loi n° 78-17", "règlement 2016/67900"):
            with self.subTest(reference=reference):
                self.assertEqual(eurlex._lire_reference(reference)[0], None)

    def test_titre_reprend_le_numero(self):
        self.assertTrue(eurlex._titre_reprend("Règlement (UE) n ° 910/2014 du Parlement", 2014, 910))
        self.assertTrue(eurlex._titre_reprend("Directive 92/43/CEE du Conseil", 1992, 43))
        self.assertFalse(eurlex._titre_reprend("Directive 2011/92/UE", 2011, 9))


class Resoudre(unittest.TestCase):
    """resoudre : existence vérifiée dans Cellar, titres fictifs."""

    def resoudre(self, reference, lignes, etat=False):
        substitut = reponses(lignes, [])
        with mock.patch("urllib.request.urlopen", substitut):
            return eurlex.resoudre(reference, etat=etat), substitut

    def test_acte_trouve(self):
        r, substitut = self.resoudre("directive 2011/92/UE", [
            ("32011L0092", "Directive 2011/92/UE concernant l'évaluation des incidences", "2011-12-13")])
        self.assertEqual((r["trouve"], r["message"], [x["celex"] for x in r["resultats"]]),
                         (True, None, ["32011L0092"]))
        x = "^^<http://www.w3.org/2001/XMLSchema#string>"
        self.assertIn(f'VALUES ?celex {{ "32011L0092"{x} "32011R0092"{x} "32011D0092"{x} }}',
                      requete_envoyee(substitut))

    def test_autres_types_seulement_si_introuvable(self):
        r, _ = self.resoudre("directive 2011/92/UE", [
            ("32011L0092", "Directive 2011/92/UE concernant l'évaluation des incidences", "2011-12-13"),
            ("32011R0092", "Règlement (UE) n° 92/2011 de la Commission", "2011-02-03")])
        self.assertEqual(r["autres"], [])

    def test_mauvais_type(self):
        r, _ = self.resoudre("directive 2016/679", [
            ("32016R0679", "Règlement (UE) 2016/679 relatif à la protection des données", "2016-04-27")])
        self.assertFalse(r["trouve"])
        self.assertEqual([x["celex"] for x in r["autres"]], ["32016R0679"])
        self.assertIn("autre type", r["message"])

    def test_introuvable(self):
        r, _ = self.resoudre("règlement (UE) 2016/6790", [])
        self.assertEqual((r["trouve"], r["resultats"], r["autres"]), (False, [], []))
        self.assertEqual(r["message"], "Introuvable dans EUR-Lex.")

    def test_titre_sans_le_numero(self):
        r, _ = self.resoudre("directive 2011/92/UE", [("32011L0092", "Directive sans numéro", "2011-12-13")])
        self.assertTrue(r["trouve"])
        self.assertIn("ne reprend pas le numéro", r["message"])

    def test_affaire(self):
        r, _ = self.resoudre("C-461/17", [
            ("62017CC0461", "Conclusions de l'avocate générale", "2018-07-12"),
            ("62017CJ0461", "Arrêt de la Cour du 7 novembre 2018", "2018-11-07")])
        self.assertTrue(r["trouve"])
        self.assertEqual([x["celex"] for x in r["resultats"]], ["62017CJ0461", "62017CC0461"])

    def test_reference_non_reconnue_pas_de_requete(self):
        r, substitut = self.resoudre("loi n° 78-17", [])
        self.assertFalse(r["trouve"])
        self.assertIn("non reconnue", r["message"])
        substitut.assert_not_called()

    def test_avec_etat(self):
        substitut = reponses([("32010L0075", "Directive 2010/75/UE relative aux émissions industrielles",
                               "2010-11-24")], ETAT_2010_75)
        with mock.patch("urllib.request.urlopen", substitut):
            r = eurlex.resoudre("directive 2010/75/UE")
        self.assertEqual(substitut.call_count, 2)
        self.assertEqual(r["resultats"][0]["version_consolidee"]["celex"], "02010L0075-20240804")

    def test_panne(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("réseau coupé")):
            with self.assertRaises(urllib.error.URLError):
                eurlex.resoudre("directive 2011/92/UE")


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
