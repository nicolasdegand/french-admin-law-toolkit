# -*- coding: utf-8 -*-
"""Travaux parlementaires d'une disposition législative (via Légifrance PISTE).

Principe : on résout la VERSION de l'article applicable à la date du litige
(ratione temporis), on identifie le texte qui a CRÉÉ cette version (lien
« CREE » de Légifrance), puis on récupère son dossier législatif et ses
travaux préparatoires (prepWork), qui recensent les pièces Assemblée nationale
et Sénat. Ne vaut que pour les dispositions législatives ; un article
réglementaire (R./D.) n'a pas de travaux parlementaires.
"""
import re
try:
    import legifrance
except Exception:
    legifrance = None


import time as _time
def _retry(fn, n=3):
    last=None
    for i in range(n):
        try:
            return fn()
        except Exception as e:
            last=e; _time.sleep(1.2*(i+1))
    raise last

def _clean(html):
    if not html:
        return ""
    t = re.sub(r"<br\s*/?>", "\n", html)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


_RE_REGLEMENTAIRE = re.compile(r"""
    \s*
    (?:l['’]\s*)?               # « l'article »
    (?:art(?:icle)?s?\.?\s*)?   # « article », « art. », en toutes casses
    [RD]                        # le préfixe, R ou D
    (?![^\W\d_])                # non suivi d'une lettre (écarte « Règlement »)
    """, re.IGNORECASE | re.VERBOSE)


def _est_reglementaire(article):
    """Vrai si l'article désigné est réglementaire, c'est-à-dire si son numéro commence par R ou D.
    Le préfixe peut être en minuscule et précédé de « article », « art. » ou « l'article » :
    « R. 181-28 », « Article R. 181-28 », « art. r. 181-28 », « D. 123-1 », « R* 122-1 ».
    Un R ou un D suivi d'une lettre (« Règlement », « Décret ») n'est pas un préfixe.
    Un article de décret non codifié, sans préfixe, n'est pas reconnu."""
    return bool(_RE_REGLEMENTAIRE.match(article or ""))


def _lien_dossier(idd):
    return f"https://www.legifrance.gouv.fr/dossierlegislatif/{idd}" if idd else None


def _lien_texte(cid):
    if not cid:
        return None
    if cid.startswith("JORFTEXT"):
        return f"https://www.legifrance.gouv.fr/loda/id/{cid}"
    return f"https://www.legifrance.gouv.fr/jorf/id/{cid}"


def travaux_pour_article(code, article, date):
    """Retourne les travaux parlementaires du texte ayant créé la version de
    <article> du <code> applicable au <date> (YYYY-MM-DD)."""
    if not legifrance:
        return {"trouve": False, "erreur": "connecteur Légifrance indisponible"}
    if _est_reglementaire(article):
        return {"trouve": False, "reglementaire": True, "article": article, "code": code,
                "message": "Disposition réglementaire : pas de travaux parlementaires."}
    # exact=True : un autre article que celui demandé (« L. 181-18 » pour « L. 181-18-1 ») est
    # écarté par legifrance.py, qui rend alors `exact` False, et le `num` et le `lien` du plus proche.
    r = legifrance.resoudre(code, article, date, exact=True)
    if not r.get("trouve"):
        if r.get("exact") is False:
            return {"trouve": False, "exact": False, "article": article, "code": code,
                    "num": r.get("num"), "lien": r.get("lien"),
                    "message": f"Article introuvable à cette date ; l'article le plus proche est {r.get('num')}."}
        return {"trouve": False, "article": article, "code": code,
                "message": "Version de l'article non résolue à cette date."}
    version = f'{r.get("version_debut")} → {r.get("version_fin") or "en cours"}'
    art = _retry(lambda: legifrance._post("/consult/getArticle", {"id": r["id"]})).get("article", {})
    # texte ayant CRÉÉ cette version
    cree = None
    for l in (art.get("lienModifications") or []):
        if l.get("linkType") == "CREE":
            cree = l
            break
    if cree is None:
        for l in (art.get("lienModifications") or []):
            if l.get("textCid"):
                cree = l
                break
    if not cree or not cree.get("textCid"):
        return {"trouve": False, "article": article, "code": code, "version": version,
                "message": "Texte créateur de la version non identifié."}
    cid = cree["textCid"]
    # consultation du texte -> dossier législatif + travaux préparatoires
    doss_id = None
    prep = ""
    nature = cree.get("natureText")
    titre = cree.get("textTitle")
    try:
        js = _retry(lambda: legifrance._post("/consult/jorf", {"textCid": cid}))
        nature = js.get("nature") or nature
        titre = js.get("title") or titre
        prep = _clean(js.get("prepWork"))
        dl = js.get("dossiersLegislatifs") or []
        if dl:
            doss_id = dl[0].get("id")
    except Exception:
        pass
    dp = dossier_pieces(doss_id) if doss_id else {"pieces": [], "expose_motif": None}
    return {
        "trouve": True, "article": article, "code": code, "version": version,
        "loi": {"titre": titre, "nature": nature, "cid": cid,
                "date_publi": cree.get("datePubliTexte")},
        "lien_texte": _lien_texte(cid),
        "lien_dossier": _lien_dossier(doss_id),
        "travaux_preparatoires": prep,
        "pieces": dp.get("pieces", []),
        "expose_motif": dp.get("expose_motif"),
        "nota": _clean(art.get("nota")),
        "ratione_temporis": "Texte ayant créé la version applicable au litige (non la rédaction actuelle).",
    }


def travaux_pour_textes(textes, date):
    """Batch sur les dispositions du litige (liste de {code, article})."""
    out = []
    for t in textes or []:
        try:
            out.append(travaux_pour_article(t["code"], t["article"], date))
        except Exception as e:
            out.append({"trouve": False, "article": t.get("article"), "code": t.get("code"),
                        "message": f"erreur: {e}"})
    return out


if __name__ == "__main__":
    import json
    for code, art, d in [("Code de l'environnement", "L. 181-18", "2020-01-01"),
                         ("Code de l'environnement", "R. 181-28", "2020-01-01")]:
        print("\n====", art, "du", code, "au", d, "====")
        res = travaux_pour_article(code, art, d)
        print(json.dumps({k: v for k, v in res.items() if k != "travaux_preparatoires"},
                         ensure_ascii=False, indent=1))
        if res.get("travaux_preparatoires"):
            print("Travaux préparatoires (extrait):")
            print(res["travaux_preparatoires"][:500])


def _pieces_from_arbo(arbo):
    """Aplati l'arborescence d'un dossier législatif en liste de pièces {libelle, lien, categorie}."""
    out = []
    def walk(node, path):
        lib = node.get("libelle")
        newpath = path + [lib] if lib else path
        for l in (node.get("liens") or []):
            if l.get("lien"):
                out.append({"libelle": l.get("libelle"), "lien": l.get("lien"),
                            "categorie": " / ".join(newpath)})
        for sub in (node.get("niveaux") or []):
            walk(sub, newpath)
    for n in (arbo.get("niveaux") or []):
        walk(n, [])
    return out

def dossier_pieces(dole_id, max_pieces=40):
    """Consulte un dossier législatif (JORFDOLE) et renvoie ses pièces avec liens
    (projet de loi, rapports, débats, exposé des motifs...) + l'exposé des motifs."""
    if not legifrance or not dole_id:
        return {"pieces": [], "expose_motif": None}
    try:
        d = _retry(lambda: legifrance._post("/consult/dossierLegislatif",
                                            {"id": dole_id})).get("dossierLegislatif", {})
    except Exception:
        return {"pieces": [], "expose_motif": None}
    pieces = _pieces_from_arbo(d.get("arborescence") or {})
    for t in (d.get("dossiers") or []):
        lib = t.get("libelleTexte"); idt = t.get("idTexte")
        if lib and idt:
            pieces.append({"libelle": lib,
                           "lien": f"https://www.legifrance.gouv.fr/jorf/id/{idt}",
                           "categorie": "Textes du dossier"})
    # dédup par lien
    seen = set(); uniq = []
    for p in pieces:
        if p["lien"] in seen:
            continue
        seen.add(p["lien"]); uniq.append(p)
    return {"pieces": uniq[:max_pieces], "expose_motif": _clean(d.get("exposeMotif"))}
