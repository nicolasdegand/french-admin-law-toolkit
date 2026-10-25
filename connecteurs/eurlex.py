# -*- coding: utf-8 -*-
"""Recherche EUR-Lex (droit de l'Union) via le point d'accès SPARQL public Cellar.

Recherche par mots-clés dans les titres français, restreinte par défaut à la
législation (secteur CELEX 3) et à la jurisprudence de l'Union (secteur 6).
Aucune authentification. Renvoie référence, type, date et lien EUR-Lex.
"""
import re, urllib.request, urllib.parse, json

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


def chercher(question, k=6, secteurs=("3", "6"), timeout=60):
    """Recherche EUR-Lex. Réponse directe aux actes « phares » détectés par sigle (DSA, DMA,
    AI Act…), complétée par une recherche par mots-clés dans les titres FR : un titre est retenu
    s'il contient l'un des mots (OU) ; les titres sont classés par nombre de mots présents, puis
    du plus récent au plus ancien, et ceux qui n'en contiennent qu'un sont écartés dès qu'un
    autre en contient au moins deux. Renvoie une liste de {reference, celex, type, titre, date,
    lien}.
    Si le point d'accès ne répond pas (réseau, délai dépassé, erreur HTTP), l'erreur remonte, comme
    dans les fonctions de recherche de legifrance.py : une panne n'est pas un résultat vide."""
    phares = _phares(question)
    mots = _mots(question)
    if not mots:
        return phares[:k]
    ors = " || ".join(f'CONTAINS(LCASE(STR(?title)), "{m}")' for m in mots)
    filtres = f"  FILTER({ors})"
    sect = " || ".join(f'STRSTARTS(STR(?celex),"{s}")' for s in secteurs)
    q = f'''PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex ?title ?date WHERE {{
  ?exp cdm:expression_uses_language <{_FRA}> ;
       cdm:expression_title ?title ;
       cdm:expression_belongs_to_work ?work .
  ?work cdm:resource_legal_id_celex ?celex .
  OPTIONAL {{ ?work cdm:work_date_document ?date }}
{filtres}
  FILTER({sect})
}} LIMIT {max(k*8, 40)}'''
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": q, "format": "application/sparql-results+json"})
    req = urllib.request.Request(url, headers={"Accept": "application/sparql-results+json",
                                               "User-Agent": "Mozilla/5.0"})
    js = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    cand, seen = [], set()
    for b in js.get("results", {}).get("bindings", []):
        celex = b.get("celex", {}).get("value", "")
        if celex in seen:
            continue
        seen.add(celex)
        title = b.get("title", {}).get("value", "")
        date = (b.get("date", {}).get("value", "") or "")[:10]
        score = sum(1 for m in mots if m in title.lower())      # nombre de termes de la requête présents
        cand.append((score, date, celex, title))
    cand = [c for c in cand if c[0] > 0]                         # au moins un terme de la requête présent
    if cand:
        mx = max(c[0] for c in cand)
        if mx >= 2:                                              # écarte le bruit à un seul terme générique
            cand = [c for c in cand if c[0] >= 2]
    cand.sort(key=lambda x: (x[0], x[1]), reverse=True)          # plus de termes d'abord, puis plus récent
    out = list(phares)                                          # actes phares en tête
    dejacelex = {p["celex"] for p in phares}
    for score, date, celex, title in cand[:k]:
        if celex in dejacelex:
            continue
        out.append({"reference": f"{_type_celex(celex)} — CELEX {celex}",
                    "celex": celex, "type": _type_celex(celex),
                    "titre": title[:220], "date": date, "lien": _lien(celex)})
    return out[:max(k, len(phares))]


if __name__ == "__main__":
    for query in ["évaluation des incidences sur l'environnement",
                  "autorisation installations classées"]:
        print("\n==", query)
        for r in chercher(query, k=4):
            print(f"  [{r['type']}] {r['celex']} {r['date']}")
            print("     ", r["titre"][:90])
            print("     ", r["lien"])
