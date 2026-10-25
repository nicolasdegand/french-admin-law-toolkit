# -*- coding: utf-8 -*-
"""Recherche EUR-Lex (droit de l'Union) via le point d'accès SPARQL public Cellar.

Recherche dans les titres français. `chercher` part d'une question rédigée
librement (législation et jurisprudence de l'Union, secteurs CELEX 3 et 6) ;
`chercher_termes` part de termes choisis par l'appelant, qui doivent tous figurer
dans le titre (législation par défaut). Aucune authentification. Renvoie
référence, type, titre, date et lien EUR-Lex, et l'état de chaque acte (en
vigueur, fin de validité, dernière version consolidée, rectificatifs).
`resoudre` retrouve un acte ou une affaire par son numéro (« directive
2011/92/UE », « C-461/17 », numéro CELEX).
"""
import datetime, re, urllib.request, urllib.parse, json

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
_FRA = "http://publications.europa.eu/resource/authority/language/FRA"

# Libellés des descripteurs CELEX (type de document), repris de la page d'EUR-Lex « Types de
# documents dans EUR-Lex » en français (consultée le 25/10/2026) :
#   https://eur-lex.europa.eu/content/tools/TableOfSectors/types_of_documents_in_eurlex.html?locale=fr
# au singulier (la page nomme des catégories : « Règlements »), avec l'auteur entre parenthèses pour
# la jurisprudence. Les « communications » du secteur 6 sont des avis publiés au JO (nouvelle
# affaire, arrêt, ordonnance), non des décisions : leur libellé le dit.
_TYPE_LEGISLATION = {          # secteur 3, actes juridiques, une lettre
    "A": "Avis", "B": "Budget", "C": "Déclaration", "D": "Décision",
    "E": "PESC : position commune, action commune ou stratégie commune (titre V du traité UE pré-Lisbonne)",
    "F": "Coopération policière et judiciaire en matière pénale (titre VI du traité UE pré-Lisbonne)",
    "G": "Résolution", "H": "Recommandation",
    "J": "Non-opposition à une entreprise commune notifiée", "K": "Recommandation CECA",
    "L": "Directive", "M": "Non-opposition à une concentration notifiée",
    "O": "Orientation de la BCE", "Q": "Disposition institutionnelle (règlement intérieur, accord interne)",
    "R": "Règlement", "S": "Décision de portée générale CECA",
    "X": "Autre document publié au JO L (ou avant 1967)", "Y": "Autre document publié au JO C",
}
_TYPE_JURISPRUDENCE = {        # secteur 6, jurisprudence de l'Union, deux lettres : C = Cour de
    # justice, T = Tribunal, F = Tribunal de la fonction publique (dissous le 1er septembre 2016)
    "CJ": "Arrêt (Cour de justice)", "CO": "Ordonnance (Cour de justice)",
    "CC": "Conclusions de l'avocat général (Cour de justice)", "CS": "Saisie-arrêt (Cour de justice)",
    "CT": "Tierce opposition (Cour de justice)", "CV": "Avis (Cour de justice)",
    "CX": "Délibération (Cour de justice)", "CD": "Décision (Cour de justice)",
    "CP": "Prise de position (Cour de justice)", "CN": "Communication : nouvelle affaire (Cour de justice)",
    "CA": "Communication : arrêt (Cour de justice)", "CB": "Communication : ordonnance (Cour de justice)",
    "CU": "Communication : demande d'avis (Cour de justice)", "CG": "Communication : avis (Cour de justice)",
    "TJ": "Arrêt (Tribunal)", "TO": "Ordonnance (Tribunal)",
    "TC": "Conclusions de l'avocat général (Tribunal)", "TT": "Tierce opposition (Tribunal)",
    "TN": "Communication : nouvelle affaire (Tribunal)", "TA": "Communication : arrêt (Tribunal)",
    "TB": "Communication : ordonnance (Tribunal)",
    "FJ": "Arrêt (Tribunal de la fonction publique)", "FO": "Ordonnance (Tribunal de la fonction publique)",
    "FT": "Tierce opposition (Tribunal de la fonction publique)",
    "FN": "Communication : nouvelle affaire (Tribunal de la fonction publique)",
    "FA": "Communication : arrêt (Tribunal de la fonction publique)",
    "FB": "Communication : ordonnance (Tribunal de la fonction publique)",
}
_TYPE_ACCORDS = {              # secteur 2, accords internationaux
    "A": "Accord avec un pays tiers ou une organisation internationale",
    "D": "Acte d'un organe créé par un accord international",
    "P": "Acte d'un organe parlementaire créé par un accord international", "X": "Autre acte",
}
_TYPE_COMPLEMENTAIRE = {       # secteur 4, législation complémentaire
    "A": "Accord entre États membres",
    "D": "Décision des représentants des gouvernements des États membres",
    "X": "Autre acte publié au JO L", "Y": "Autre acte publié au JO C", "Z": "Législation complémentaire",
}
_TYPE_PAR_SECTEUR = {"2": _TYPE_ACCORDS, "3": _TYPE_LEGISLATION, "4": _TYPE_COMPLEMENTAIRE}


def _type_celex(celex):
    """Type de document d'après le numéro CELEX : secteur (1er chiffre) et descripteur (lettres
    qui suivent l'année). « 32016R0679 » -> Règlement ; « 62019CJ0123 » -> Arrêt (Cour de justice)."""
    m = re.match(r"^([1-9])(\d{4})([A-Z]{1,2})", celex or "")
    if not m:
        return "Document"
    sect, _, desc = m.groups()
    if sect == "6":
        return _TYPE_JURISPRUDENCE.get(desc, "Jurisprudence de l'Union")
    if sect == "5":
        return "Document préparatoire"
    return _TYPE_PAR_SECTEUR.get(sect, {}).get(desc[:1], "Acte de l'Union")


def _lien(celex):
    return f"https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:{celex}"


def _mots(question, n=8):
    stop = {"dans","pour","avec","cette","les","des","une","aux","sur","par","que","qui","est","sont",
            "selon","entre","leur","plus","doit","etre","être","ainsi","dont","elle",
            # bruit procédural (n'aide pas la recherche thématique EUR-Lex)
            "appel","appelant","requete","requête","requérant","requerant","annulation","annuler","jugement",
            "arret","arrêt","tribunal","cour","instance","demande","demandeur","rejete","rejeté","rejet",
            "restitution","decharge","décharge","moyen","moyens","tendant","contestation","litige","dossier",
            "considerant","considérant","article","articles","alinea","alinéa","code","montant","somme",
            "annees","années","titre","fins","memoire","mémoire","defense","défense","piece","pièces",
            "societe","société","application","méconnaissance","meconnaissance","fondee","fondée","fonde"}
    # acronymes/sigles étendus vers la terminologie EUR-Lex (les titres de l'UE n'emploient pas « TVA »)
    expand = {"tva": "taxe valeur ajoutée", "rgpd": "données caractère personnel",
              "oqtf": "retour ressortissant pays tiers séjour irrégulier",
              "icpe": "émissions industrielles accidents majeurs substances dangereuses",
              "dpi": "propriété intellectuelle",
              "dsa": "marché unique services numériques", "digital services act": "marché unique services numériques",
              "dma": "marchés contestables équitables secteur numérique",
              "digital markets act": "marchés contestables équitables secteur numérique",
              "ai act": "intelligence artificielle", "iaa": "intelligence artificielle",
              "ria": "intelligence artificielle", "règlement ia": "intelligence artificielle",
              "nis2": "niveau élevé commun cybersécurité", "nis 2": "niveau élevé commun cybersécurité",
              "dora": "résilience opérationnelle numérique secteur financier",
              "data act": "règles harmonisées équité accès données utilisation données",
              "data governance act": "gouvernance européenne données",
              "mdr": "dispositifs médicaux", "csrd": "publication informations durabilité entreprises",
              "eidas": "identification électronique services confiance"}
    q = (question or "")
    for sig, terme in expand.items():
        q = re.sub(r"\b" + sig + r"\b", " " + terme + " ", q, flags=re.IGNORECASE)
    # acronymes purement français à ignorer (absents des titres de l'Union)
    dom = {"lpf","cgi","cja","ce","ca3","ca","ceseda","cgct","csp","css","crpa","cerfa","cade","ta","caa","cc"}
    raw = re.split(r"[^0-9A-Za-zà-ÿÀ-Ÿ]+", q)
    toks = [w for w in (t.lower() for t in raw) if len(w) > 3 and w not in stop and w not in dom]
    toks = list(dict.fromkeys(sorted(dict.fromkeys(toks), key=len, reverse=True)))[:n]
    return toks


# Actes européens « phares » identifiables par un sigle : réponse directe et exacte,
# le sigle n'apparaissant pas dans le titre officiel (recherche par mots-clés inefficace).
# Chaque entrée : motif, numéro CELEX, date de l'acte (AAAA-MM-JJ), titre.
# Numéros et dates vérifiés le 25/10/2026. Une entrée est à mettre à jour quand l'acte est
# abrogé ou remplacé : le module le rendrait sinon sans avertissement.
_ACTES_PHARES = [
    (r"\b(dsa|digital services act|r[eè]glement sur les services num[ée]riques)\b", "32022R2065", "2022-10-19",
     "Règlement (UE) 2022/2065 relatif à un marché unique des services numériques (règlement sur les services numériques — DSA)"),
    (r"\b(dma|digital markets act|r[eè]glement sur les march[ée]s num[ée]riques)\b", "32022R1925", "2022-09-14",
     "Règlement (UE) 2022/1925 relatif aux marchés contestables et équitables dans le secteur numérique (DMA)"),
    (r"\b(ai act|r[eè]glement (sur l['’ ]?)?ia|intelligence artificielle)\b", "32024R1689", "2024-06-13",
     "Règlement (UE) 2024/1689 établissant des règles harmonisées concernant l'intelligence artificielle (règlement sur l'IA)"),
    (r"\b(data act|r[eè]glement sur les donn[ée]es)\b", "32023R2854", "2023-12-13",
     "Règlement (UE) 2023/2854 (règlement sur les données — Data Act)"),
    (r"\b(data governance act|gouvernance des donn[ée]es|dga)\b", "32022R0868", "2022-05-30",
     "Règlement (UE) 2022/868 portant sur la gouvernance européenne des données (DGA)"),
    (r"\b(nis ?2|directive sri ?2)\b", "32022L2555", "2022-12-14",
     "Directive (UE) 2022/2555 (SRI 2 / NIS 2) — cybersécurité"),
    (r"\bdora\b", "32022R2554", "2022-12-14",
     "Règlement (UE) 2022/2554 sur la résilience opérationnelle numérique du secteur financier (DORA)"),
    (r"\b(rgpd|gdpr)\b", "32016R0679", "2016-04-27",
     "Règlement (UE) 2016/679 (protection des données — RGPD)"),
    (r"\b(csrd)\b", "32022L2464", "2022-12-14",
     "Directive (UE) 2022/2464 (publication d'informations en matière de durabilité — CSRD)"),
    (r"\beidas\b", "32014R0910", "2014-07-23",
     "Règlement (UE) n° 910/2014 (identification électronique et services de confiance — eIDAS)"),
]


def _phares(question):
    out, vus = [], set()
    for pat, celex, date, titre in _ACTES_PHARES:
        if celex in vus:
            continue
        if re.search(pat, question or "", flags=re.IGNORECASE):
            vus.add(celex)
            out.append({"reference": "%s — CELEX %s" % (_type_celex(celex), celex), "celex": celex,
                        "type": _type_celex(celex), "titre": titre, "date": date, "lien": _lien(celex)})
    return out


def _executer(requete, timeout):
    """Envoie la requête SPARQL au point d'accès et rend [(celex, titre, date)], un par numéro
    CELEX, dans l'ordre du point d'accès. Une panne lève l'erreur."""
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": requete, "format": "application/sparql-results+json"})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json",
                                               "User-Agent": "Mozilla/5.0"})
    js = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    lignes, vus = [], set()
    for b in js.get("results", {}).get("bindings", []):
        celex = b.get("celex", {}).get("value", "")
        if celex in vus:
            continue
        vus.add(celex)
        lignes.append((celex, b.get("title", {}).get("value", ""),
                       (b.get("date", {}).get("value", "") or "")[:10]))
    return lignes


def _resultat(celex, titre, date):
    """Un document tel que le rendent les fonctions de recherche."""
    return {"reference": f"{_type_celex(celex)} — CELEX {celex}", "celex": celex,
            "type": _type_celex(celex), "titre": titre[:220], "date": date, "lien": _lien(celex)}


def _formes(mot):
    """Le mot et sa forme au pluriel ou au singulier, écrites en toutes lettres (l'index plein
    texte compare des mots entiers ; un joker « mot* » s'y est révélé beaucoup trop lent). Règles
    sommaires : une forme inexistante (« oiseal » pour « oiseaux ») est sans effet sur la
    recherche."""
    f = {mot, mot[:-1] if mot.endswith(("s", "x")) else mot + "s"}
    if mot.endswith("al"):
        f.add(mot[:-2] + "aux")
    if mot.endswith("aux"):
        f.add(mot[:-3] + "al")
    return sorted(f)


def _expression_paires(mots, n=6):
    """Expression pour l'index plein texte : titres qui contiennent au moins deux des `n` premiers
    mots, chacun sous l'une de ses formes ; un seul mot s'il n'y en a qu'un."""
    groupes = ["(" + " OR ".join(f'"{f}"' for f in _formes(m)) + ")" for m in mots[:n]]
    if len(groupes) == 1:
        return groupes[0]
    return " OR ".join(f"({a} AND {b})" for i, a in enumerate(groupes) for b in groupes[i + 1:])


# Numéros CELEX qui doublent un autre document : rectificatif (« R(01) »), résumé (« _SUM »,
# « _RES »), fiche d'information (« _INF »).
_DOUBLONS = ("R(", "_SUM", "_RES", "_INF")


def _candidats(expression, secteur, timeout, limite=100):
    """Titres d'un secteur CELEX qui répondent à l'expression, par l'index plein texte."""
    doublons = " && ".join(f'!CONTAINS(STR(?celex), "{d}")' for d in _DOUBLONS)
    q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?title ?date ?sc WHERE {{
  ?exp cdm:expression_title ?title .
  ?title bif:contains '{expression}' OPTION (score ?sc) .
  ?exp cdm:expression_uses_language <{_FRA}> ;
       cdm:expression_belongs_to_work ?work .
  ?work cdm:resource_legal_id_celex ?celex .
  OPTIONAL {{ ?work cdm:work_date_document ?date }}
  FILTER(STRSTARTS(STR(?celex), "{secteur}"))
  FILTER({doublons})
}} ORDER BY DESC(?sc) LIMIT {limite}"""
    return _executer(q, timeout)


def _en_vigueur(celex, timeout):
    """{celex: True ou False} pour les actes dont Cellar indique s'ils sont en vigueur."""
    if not celex:
        return {}
    q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?bc ?v WHERE {{
  VALUES ?bc {{ {_valeurs_celex(celex)} }}
  ?base cdm:resource_legal_id_celex ?bc .
  ?base cdm:resource_legal_in-force ?v
}}"""
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": q, "format": "application/sparql-results+json"})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json",
                                               "User-Agent": "Mozilla/5.0"})
    js = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    out = {}
    for b in js.get("results", {}).get("bindings", []):
        if "bc" in b and "v" in b:
            out[b["bc"]["value"]] = b["v"]["value"].lower() in ("1", "true")
    return out


def _rang_type(celex):
    """Législation : directives et règlements, puis décisions, puis recommandations, puis le
    reste. Jurisprudence : arrêts, conclusions et ordonnances, puis communications au JO."""
    if celex[:1] == "3" and len(celex) > 5:
        return {"L": 0, "R": 0, "D": 1, "F": 1, "H": 2}.get(celex[5], 3)
    if celex[:1] == "6" and len(celex) > 6:
        return 0 if celex[6] in "JCO" else 1
    return 3


def _classer(mots, lignes, vigueur):
    """Classement des titres candidats : nombre de mots de la question présents (sous l'une de
    leurs formes), puis actes en vigueur avant actes abrogés, puis « projets » et rectificatifs
    après les actes, puis selon le type (`_rang_type`), puis titre le plus court (l'acte de base
    a souvent un titre plus court que les actes qui le modifient ou l'appliquent)."""
    def cle(ligne):
        celex, titre, _ = ligne
        t = titre.lower()
        presents = sum(1 for m in mots if any(f in t for f in _formes(m)))
        return (-presents, vigueur.get(celex) is False, t.startswith(("projet", "rectificatif")),
                _rang_type(celex), len(titre))
    return sorted(lignes, key=cle)


def chercher(question, k=6, secteurs=("3", "6"), timeout=60, etat=True):
    """Recherche EUR-Lex à partir d'une question rédigée librement.

    Sont rendus, dans cet ordre, sans doublon :
    1. les actes « phares » reconnus par leur sigle (RGPD, DSA, AI Act…) ;
    2. l'acte ou l'affaire dont la question cite le numéro (« la directive 2011/92/UE… »), par
       `resoudre` ;
    3. pour chaque secteur CELEX de `secteurs`, dans l'ordre (législation, puis jurisprudence par
       défaut), jusqu'à `k` documents dont le titre contient au moins deux mots de la question,
       trouvés par l'index plein texte et classés par `_classer`.
    Les actes d'abord, la jurisprudence ensuite : mélangés, les titres d'arrêts, qui reprennent le
    sommaire de l'affaire, passaient devant les actes. Mesure sur deux bancs de questions :
    bancs/eurlex/. Pour un acte connu, `resoudre` est plus sûre ; pour un thème, `chercher_termes`,
    avec les mots de l'intitulé : une question rédigée en termes de droit français (« SDAGE »,
    « étude d'impact ») ne rencontre pas le vocabulaire des actes de l'Union.

    Renvoie une liste de {reference, celex, type, titre, date, lien}, complétée par l'état de
    chaque acte si `etat` est vrai (voir `etat_des_actes`).
    Si le point d'accès ne répond pas (réseau, délai dépassé, erreur HTTP), l'erreur remonte, comme
    dans les fonctions de recherche de legifrance.py : une panne n'est pas un résultat vide."""
    out = list(_phares(question))
    cite = resoudre(question, etat=False, timeout=timeout) if _lire_reference(question)[0] in ("acte", "affaire") else None
    if cite:
        out += cite["resultats"]
    mots = [m for m in _mots(question) if not m.isdigit()]
    if mots:
        expression = _expression_paires(mots)
        for secteur in secteurs:
            lignes = _candidats(expression, secteur, timeout)
            vigueur = _en_vigueur([c for c, _, _ in lignes], timeout) if secteur == "3" else {}
            out += [_resultat(c, t, d) for c, t, d in _classer(mots, lignes, vigueur)[:k]]
    vus, uniques = set(), []
    for r in out:
        if r["celex"] not in vus:
            vus.add(r["celex"])
            uniques.append(r)
    return _avec_etat(uniques, timeout) if etat else uniques



def _expression_plein_texte(terme):
    """Terme -> expression exacte pour l'index plein texte (« "valeur ajoutée" ») : caractères
    autres que lettres, chiffres, espaces et tirets remplacés par des espaces, car ils ont un
    sens pour l'index ou termineraient la chaîne SPARQL. L'apostrophe devient une espace, comme
    dans l'index (« d'environnement » -> « d environnement ») : retirer la lettre élidée ferait
    manquer l'expression. None si rien ne reste."""
    t = " ".join(re.sub(r"[^\w\s-]", " ", terme).split())
    return f'"{t}"' if t else None


# Numéro CELEX d'un rectificatif : celui de l'acte rectifié suivi de « R(nn) ».
_RE_RECTIFICATIF = re.compile(r"^(.+)R\(\d+\)$")


def chercher_termes(termes, k=6, secteurs=("3",), timeout=60, etat=True):
    """Recherche EUR-Lex des documents dont le titre français contient TOUS les termes (ET),
    choisis par l'appelant : ni extraction de mots, ni remplacement de sigles, ni actes phares.

    La recherche passe par l'index plein texte du point d'accès (`bif:contains`, extension de
    Virtuoso, logiciel du point d'accès, et non du SPARQL standard) : réponse en une seconde
    environ, titres classés par pertinence. Un terme est un mot ou une expression, cherché tel
    quel, sans tenir compte des majuscules : « projet » ne trouve pas « projets », « faune et
    flore » ne trouve pas « de la faune et de la flore ». Reprendre les mots de l'intitulé.

    Par défaut, la législation seule (secteur 3) ; secteurs=("3", "6") y ajoute la jurisprudence.
    Un rectificatif trouvé avec son acte (numéro de l'acte suivi de « R(nn) ») ne prend pas de
    place dans les résultats : son numéro figure dans le champ `rectificatifs` de l'acte. Les
    résumés d'arrêts (« _SUM »), qui doublent l'arrêt, sont écartés.
    Mesure sur un banc de questions : bancs/eurlex/.
    Renvoie une liste de {reference, celex, type, titre, date, lien, rectificatifs}, vide si aucun
    terme n'est donné. Si `etat` est vrai, chaque acte porte en outre son état (voir
    `etat_des_actes`) et `rectificatifs` la liste complète de ses rectificatifs ; sinon, ce
    champ ne liste que ceux dont le titre contient les termes, et vide il ne prouve pas qu'il
    n'en existe aucun. Si le point d'accès ne répond pas, l'erreur remonte, comme dans
    `chercher`."""
    if isinstance(termes, str):
        termes = [termes]
    expressions = [e for e in (_expression_plein_texte(t) for t in (termes or []) if t) if e]
    if not expressions:
        return []
    sect = " || ".join(f'STRSTARTS(STR(?celex),"{s}")' for s in secteurs)
    q = f'''PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?title ?date ?sc WHERE {{
  ?exp cdm:expression_title ?title .
  ?title bif:contains '{" AND ".join(expressions)}' OPTION (score ?sc) .
  ?exp cdm:expression_uses_language <{_FRA}> ;
       cdm:expression_belongs_to_work ?work .
  ?work cdm:resource_legal_id_celex ?celex .
  OPTIONAL {{ ?work cdm:work_date_document ?date }}
  FILTER({sect})
  FILTER(!CONTAINS(STR(?celex), "_SUM"))
}} ORDER BY DESC(?sc) LIMIT {max(k * 3, 30)}'''
    lignes = _executer(q, timeout)
    trouves = {celex for celex, _, _ in lignes}
    rectificatifs, out = {}, []
    for celex, titre, date in lignes:
        m = _RE_RECTIFICATIF.match(celex)
        if m and m.group(1) in trouves:
            rectificatifs.setdefault(m.group(1), []).append(celex)
        else:
            out.append(_resultat(celex, titre, date))
    for r in out:
        r["rectificatifs"] = rectificatifs.get(r["celex"], [])
    return _avec_etat(out[:k], timeout) if etat else out[:k]



# Date de fin de validité que Cellar donne aux actes sans terme.
_SANS_FIN = "9999-12-31"


def _valeurs_celex(celex):
    """Numéros CELEX pour une clause VALUES. Cellar les enregistre comme littéraux xsd:string :
    écrits ainsi, ils sont trouvés par l'index (un dixième de seconde), alors qu'un filtre sur
    STR(?celex) parcourt tous les numéros (plusieurs secondes) et qu'un littéral sans type ne
    trouve rien."""
    return " ".join(f'"{c}"^^<http://www.w3.org/2001/XMLSchema#string>' for c in celex)


def etat_des_actes(celex, timeout=60):
    """État de chaque acte, en une seule requête : {celex: {en_vigueur, fin_de_validite,
    version_consolidee, rectificatifs}}.

    - en_vigueur : True ou False selon Cellar, None si Cellar n'en dit rien (jurisprudence…) ;
    - fin_de_validite : date AAAA-MM-JJ, None si l'acte est sans terme ;
    - version_consolidee : la plus récente, {celex, date, lien}, None s'il n'y en a pas. Une
      version consolidée est un outil de documentation : seul le texte publié au Journal
      officiel fait foi ;
    - rectificatifs : numéros CELEX de tous les rectificatifs de l'acte, liste complète.

    Cellar rattache à un acte, outre ses propres versions consolidées, celles d'actes qu'il
    modifie ou abroge : seules comptent celles dont le numéro reprend celui de l'acte (secteur 0,
    « 02010L0075-20240804 » pour 32010L0075). Une panne lève l'erreur."""
    celex = [c for c in dict.fromkeys(celex) if c and re.fullmatch(r"[0-9A-Z()_.-]+", c)]
    etats = {c: {"en_vigueur": None, "fin_de_validite": None, "version_consolidee": None,
                 "rectificatifs": []} for c in celex}
    if not celex:
        return etats
    q = f'''PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?bc ?genre ?v ?c ?d WHERE {{
  VALUES ?bc {{ {_valeurs_celex(celex)} }}
  ?base cdm:resource_legal_id_celex ?bc .
  {{ BIND("etat" AS ?genre)
     OPTIONAL {{ ?base cdm:resource_legal_in-force ?v }}
     OPTIONAL {{ ?base cdm:resource_legal_date_end-of-validity ?d }} }}
  UNION
  {{ BIND("consolidee" AS ?genre)
     ?x cdm:act_consolidated_consolidates_resource_legal ?base .
     ?x cdm:resource_legal_id_celex ?c }}
  UNION
  {{ BIND("rectificatif" AS ?genre)
     ?x cdm:resource_legal_corrects_resource_legal ?base .
     ?x cdm:resource_legal_id_celex ?c }}
}}'''
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": q, "format": "application/sparql-results+json"})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json",
                                               "User-Agent": "Mozilla/5.0"})
    js = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    for b in js.get("results", {}).get("bindings", []):
        val = {k: v.get("value", "") for k, v in b.items()}
        e = etats.get(val.get("bc"))
        if e is None:
            continue
        genre = val.get("genre")
        if genre == "etat":
            if val.get("v"):
                e["en_vigueur"] = val["v"].lower() in ("1", "true")
            fin = val.get("d", "")[:10]
            if fin and fin != _SANS_FIN:
                e["fin_de_validite"] = fin
        elif genre == "rectificatif" and val.get("c") and val["c"] not in e["rectificatifs"]:
            e["rectificatifs"].append(val["c"])
        elif genre == "consolidee":
            m = re.fullmatch(re.escape("0" + val["bc"][1:]) + r"-(\d{4})(\d{2})(\d{2})", val.get("c", ""))
            if m:
                date = "-".join(m.groups())
                if not e["version_consolidee"] or date > e["version_consolidee"]["date"]:
                    e["version_consolidee"] = {"celex": val["c"], "date": date, "lien": _lien(val["c"])}
    for e in etats.values():
        e["rectificatifs"].sort()
    return etats


def _avec_etat(resultats, timeout):
    """Ajoute à chaque résultat l'état de l'acte (`etat_des_actes`), en une requête. Les
    rectificatifs déjà rattachés au résultat sont conservés."""
    if not resultats:
        return resultats
    etats = etat_des_actes([r["celex"] for r in resultats], timeout)
    for r in resultats:
        e = dict(etats.get(r["celex"]) or {})
        e["rectificatifs"] = sorted(set(r.get("rectificatifs", [])) | set(e.get("rectificatifs", [])))
        r.update(e)
    return resultats



# --- Résolution d'une référence : numéro d'acte, numéro d'affaire, numéro CELEX ----------------

# Type d'acte -> lettre du numéro CELEX (secteur 3).
_LETTRE_ACTE = {"règlement": "R", "directive": "L", "décision": "D", "décision-cadre": "F",
                "recommandation": "H"}
_RE_ACTE = re.compile(
    r"\b(règlement|directive|décision-cadre|décision|recommandation)\b"
    r"[^0-9/]{0,60}?(n[°º]\s*|no\s+)?(\d{1,4})\s*/\s*(\d{1,4})\b", re.IGNORECASE)
# Affaire : C- (Cour de justice), T- (Tribunal), F- (Tribunal de la fonction publique).
_RE_AFFAIRE = re.compile(r"\b([CTF])\s*-\s*(\d{1,4})\s*/\s*(\d{2}|\d{4})\b")
_DOCUMENTS_AFFAIRE = {"C": ("CJ", "CC", "CO"), "T": ("TJ", "TO"), "F": ("FJ", "FO")}
_RE_CELEX = re.compile(r"[0-9]\d{4}[A-Z]{1,2}\d{4}(?:\(\d{2}\))?|0\d{4}[A-Z]\d{4}-\d{8}")
_ANNEE_COURANTE = datetime.date.today().year


def _annee(texte):
    """Année écrite sur deux chiffres (numérotation antérieure à 1999) ou quatre."""
    return 1900 + int(texte) if len(texte) == 2 else int(texte)


def _lire_reference(reference):
    """Référence -> (genre, numéros CELEX à chercher, numéro attendu dans le titre).

    genre : "celex", "acte" ou "affaire" ; None si la référence n'est pas reconnue. Pour un acte,
    le premier numéro est celui du type cité, les suivants ceux des autres types (même année,
    même numéro), pour signaler une référence qui se trompe de type.

    Règles de numérotation : depuis 2015, tous les actes sont numérotés (UE) AAAA/N. Avant,
    directives, recommandations et décisions-cadres portent l'année en premier (92/43/CEE,
    2008/98/CE), les règlements le numéro en premier (n° 1013/2006), les décisions l'année en
    premier, sauf celles qui sont numérotées « n° » (décision n° 1386/2013/UE)."""
    texte = re.sub(r"[‐-―−]", "-", reference or "").strip()
    if _RE_CELEX.fullmatch(texte.upper()):
        return "celex", [texte.upper()], None
    m = _RE_AFFAIRE.search(texte)
    if m:
        cour, numero, an = m.group(1), int(m.group(2)), m.group(3)
        annee = (1900 if int(an) >= 54 else 2000) + int(an) if len(an) == 2 else int(an)
        return "affaire", [f"6{annee}{d}{numero:04d}" for d in _DOCUMENTS_AFFAIRE[cour]], None
    m = _RE_ACTE.search(texte)
    if not m:
        return None, [], None
    type_acte, numero_d_abord = m.group(1).lower(), bool(m.group(2))
    a, b = m.group(3), m.group(4)
    if type_acte == "règlement":
        annee_d_abord = len(a) == 4 and 2015 <= int(a) <= _ANNEE_COURANTE + 1
    elif type_acte == "décision":
        annee_d_abord = not numero_d_abord
    else:
        annee_d_abord = True
    annee, numero = (_annee(a), int(b)) if annee_d_abord else (_annee(b), int(a))
    if numero > 9999:
        return None, [], None
    lettres = [_LETTRE_ACTE[type_acte]] + [l for l in "RLD" if l != _LETTRE_ACTE[type_acte]]
    return "acte", [f"3{annee}{l}{numero:04d}" for l in lettres], (annee, numero)


def _titre_reprend(titre, annee, numero):
    """Le titre cite-t-il le numéro (année et numéro, dans un ordre ou l'autre) ?"""
    an = rf"(?:{annee}|{annee % 100:02d})"
    num = rf"0*{numero}"
    return bool(re.search(rf"(?<!\d){an}\s*/\s*{num}(?!\d)|(?<!\d){num}\s*/\s*{an}(?!\d)", titre))


def resoudre(reference, etat=True, timeout=60):
    """Retrouve dans EUR-Lex l'acte ou l'affaire que désigne une référence, telle qu'on l'écrit :
    « directive 2011/92/UE », « règlement (CE) n° 1013/2006 », « directive 92/43/CEE »,
    « décision n° 1386/2013/UE », « C-461/17 », ou un numéro CELEX.

    Le numéro CELEX est déduit de la référence, puis son existence vérifiée dans Cellar. Rend
    {demande, trouve, resultats, autres, message} :
    - trouve : l'acte ou l'affaire existe ;
    - resultats : l'acte, ou les documents de l'affaire (arrêt, conclusions, ordonnances), avec
      les champs de `chercher` et, si `etat` est vrai, leur état (voir `etat_des_actes`) ;
    - autres : seulement si l'acte est introuvable sous le type cité, les actes de même année et
      de même numéro sous un autre type (« directive 2016/679 » : le règlement 2016/679 existe) ;
    - message : ce qui ne va pas (référence non reconnue, introuvable, titre qui ne reprend pas
      le numéro cité), sinon None.
    Si le point d'accès ne répond pas, l'erreur remonte."""
    genre, candidats, numero_attendu = _lire_reference(reference)
    reponse = {"demande": reference, "trouve": False, "resultats": [], "autres": [], "message": None}
    if not genre:
        reponse["message"] = "Référence non reconnue : ni numéro d'acte, ni numéro d'affaire, ni numéro CELEX."
        return reponse
    q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?title ?date WHERE {{
  VALUES ?celex {{ {_valeurs_celex(candidats)} }}
  ?work cdm:resource_legal_id_celex ?celex .
  ?exp cdm:expression_belongs_to_work ?work ;
       cdm:expression_uses_language <{_FRA}> ;
       cdm:expression_title ?title .
  OPTIONAL {{ ?work cdm:work_date_document ?date }}
}}"""
    trouves = {celex: _resultat(celex, titre, date) for celex, titre, date in _executer(q, timeout)}
    if genre == "acte":
        principal = trouves.get(candidats[0])
        reponse["resultats"] = [principal] if principal else []
        if not principal:
            reponse["autres"] = [trouves[c] for c in candidats[1:] if c in trouves]
    else:
        reponse["resultats"] = [trouves[c] for c in candidats if c in trouves]
    reponse["trouve"] = bool(reponse["resultats"])
    if not reponse["trouve"]:
        reponse["message"] = "Introuvable dans EUR-Lex" + (
            " sous ce type ; un acte de même numéro existe sous un autre type." if reponse["autres"] else ".")
    elif numero_attendu and not _titre_reprend(reponse["resultats"][0]["titre"], *numero_attendu):
        reponse["message"] = "Le titre de l'acte trouvé ne reprend pas le numéro cité : à vérifier."
    if etat:
        _avec_etat(reponse["resultats"] + reponse["autres"], timeout)
    return reponse


if __name__ == "__main__":
    for query in ["évaluation des incidences sur l'environnement",
                  "autorisation installations classées"]:
        print("\n==", query)
        for r in chercher(query, k=4):
            print(f"  [{r['type']}] {r['celex']} {r['date']}")
            print("     ", r["titre"][:90])
            print("     ", r["lien"])
