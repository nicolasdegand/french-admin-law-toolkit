# -*- coding: utf-8 -*-
"""Recherche EUR-Lex (droit de l'Union) via le point d'accès SPARQL public Cellar.

Recherche par mots-clés dans les titres français, restreinte par défaut à la
législation (secteur CELEX 3) et à la jurisprudence de l'Union (secteur 6).
Aucune authentification. Renvoie référence, type, date et lien EUR-Lex.
"""
import re, urllib.request, urllib.parse, json

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
_FRA = "http://publications.europa.eu/resource/authority/language/FRA"

# libellés des descripteurs CELEX les plus courants
_TYPE = {
    "R": "Règlement", "L": "Directive", "D": "Décision", "H": "Recommandation",
    "A": "Accord", "M": "Mesure", "X": "Autre",
    "CJ": "Arrêt (Cour de justice)", "CO": "Ordonnance (Cour de justice)",
    "CC": "Conclusions de l'avocat général", "TJ": "Arrêt (Tribunal)",
    "TO": "Ordonnance (Tribunal)", "CB": "Ordonnance", "CN": "Affaire (communication)",
}


def _type_celex(celex):
    m = re.match(r"^([1-9])(\d{4})([A-Z]{1,2})", celex or "")
    if not m:
        return "Document"
    sect, _, desc = m.groups()
    if sect == "6":
        return _TYPE.get(desc, "Jurisprudence de l'Union")
    return _TYPE.get(desc[:1], "Acte de l'Union")


def _lien(celex):
    return f"https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:{celex}"


def _mots(question, n=8):
    stop = {"dans","pour","avec","cette","les","des","une","aux","sur","par","que","qui","est","sont",
            "selon","entre","leur","plus","doit","etre","être","ainsi","dont","cette","elle","aux",
            # bruit procédural (n'aide pas la recherche thématique EUR-Lex)
            "appel","appelant","requete","requête","requérant","requerant","annulation","annuler","jugement",
            "arret","arrêt","tribunal","cour","instance","demande","demandeur","rejete","rejeté","rejet",
            "restitution","decharge","décharge","moyen","moyens","tendant","contestation","litige","dossier",
            "considerant","considérant","article","articles","alinea","alinéa","code","montant","somme",
            "annees","années","titre","fins","memoire","mémoire","defense","défense","piece","pièces",
            "societe","société","application","méconnaissance","meconnaissance","fondee","fondée","fonde"}
    # acronymes/sigles étendus vers la terminologie EUR-Lex (les titres de l'UE n'emploient pas « TVA »)
    expand = {"tva": "taxe valeur ajoutée", "rgpd": "données caractère personnel",
              "oqtf": "éloignement ressortissant pays tiers", "icpe": "installations classées environnement",
              "dpi": "propriété intellectuelle",
              "dsa": "marché unique services numériques", "digital services act": "marché unique services numériques",
              "dma": "marchés contestables équitables secteur numérique", "digital markets act": "marchés numériques",
              "ai act": "intelligence artificielle", "iaa": "intelligence artificielle",
              "ria": "intelligence artificielle", "règlement ia": "intelligence artificielle",
              "nis2": "sécurité réseaux systèmes information", "nis 2": "sécurité réseaux systèmes information",
              "dora": "résilience opérationnelle numérique secteur financier",
              "data act": "règles harmonisées équité accès données utilisation données",
              "data governance act": "gouvernance européenne données",
              "mdr": "dispositifs médicaux", "csrd": "publication informations durabilité entreprises",
              "eidas": "identification électronique services confiance"}
    q = (question or "")
    for sig, terme in expand.items():
        q = re.sub(r"\b" + sig + r"\b", " " + terme + " ", q, flags=re.IGNORECASE)
    # acronymes purement français à ignorer (absents des titres de l'Union)
    dom = {"lpf","cgi","cja","ce","ca3","ca","ceseda","cgct","csp","css","crpa","cerfa","cade","cja","ta","caa","cc"}
    raw = re.split(r"[^0-9A-Za-zà-ÿÀ-Ÿ]+", q)
    toks = [w for w in (t.lower() for t in raw) if len(w) > 3 and w not in stop and w not in dom]
    toks = list(dict.fromkeys(sorted(dict.fromkeys(toks), key=len, reverse=True)))[:n]
    return toks


# Actes européens « phares » identifiables par un sigle : réponse directe et exacte,
# le sigle n'apparaissant pas dans le titre officiel (recherche par mots-clés inefficace).
_ACTES_PHARES = [
    (r"\b(dsa|digital services act|r[eè]glement sur les services num[ée]riques)\b", "32022R2065",
     "Règlement (UE) 2022/2065 relatif à un marché unique des services numériques (règlement sur les services numériques — DSA)"),
    (r"\b(dma|digital markets act|r[eè]glement sur les march[ée]s num[ée]riques)\b", "32022R1925",
     "Règlement (UE) 2022/1925 relatif aux marchés contestables et équitables dans le secteur numérique (DMA)"),
    (r"\b(ai act|r[eè]glement (sur l['’ ]?)?ia|intelligence artificielle)\b", "32024R1689",
     "Règlement (UE) 2024/1689 établissant des règles harmonisées concernant l'intelligence artificielle (règlement sur l'IA)"),
    (r"\b(data act|r[eè]glement sur les donn[ée]es)\b", "32023R2854",
     "Règlement (UE) 2023/2854 (règlement sur les données — Data Act)"),
    (r"\b(data governance act|gouvernance des donn[ée]es|dga)\b", "32022R0868",
     "Règlement (UE) 2022/868 portant sur la gouvernance européenne des données (DGA)"),
    (r"\b(nis ?2|directive sri ?2)\b", "32022L2555",
     "Directive (UE) 2022/2555 (SRI 2 / NIS 2) — cybersécurité"),
    (r"\bdora\b", "32022R2554",
     "Règlement (UE) 2022/2554 sur la résilience opérationnelle numérique du secteur financier (DORA)"),
    (r"\b(rgpd|gdpr)\b", "32016R0679",
     "Règlement (UE) 2016/679 (protection des données — RGPD)"),
    (r"\b(csrd)\b", "32022L2464",
     "Directive (UE) 2022/2464 (publication d'informations en matière de durabilité — CSRD)"),
    (r"\beidas\b", "32014R0910",
     "Règlement (UE) n° 910/2014 (identification électronique et services de confiance — eIDAS)"),
]


def _phares(question):
    out, vus = [], set()
    for pat, celex, titre in _ACTES_PHARES:
        if celex in vus:
            continue
        if re.search(pat, question or "", flags=re.IGNORECASE):
            vus.add(celex)
            out.append({"reference": "%s — CELEX %s" % (_type_celex(celex), celex), "celex": celex,
                        "type": _type_celex(celex), "titre": titre, "date": "", "lien": _lien(celex)})
    return out


def chercher(question, k=6, secteurs=("3", "6"), timeout=60):
    """Recherche EUR-Lex. Réponse directe aux actes « phares » détectés par sigle (DSA, DMA,
    AI Act…), complétée par une recherche par mots-clés (ET) dans les titres FR. Renvoie une
    liste de {reference, celex, type, date, lien}.
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
