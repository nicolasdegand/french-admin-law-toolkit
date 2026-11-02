# -*- coding: utf-8 -*-
"""Travaux parlementaires d'une disposition législative (via Légifrance PISTE).

Principe : on résout la VERSION de l'article applicable à la date du litige
(ratione temporis), on identifie le ou les textes qui ont produit cette version
(liens de modification de Légifrance, voir `legifrance.textes_de_version`), puis
on récupère leur dossier législatif et leurs travaux préparatoires (prepWork),
qui recensent les pièces Assemblée nationale et Sénat. Ne vaut que pour les dispositions législatives ; un article
réglementaire (R./D.) n'a pas de travaux parlementaires.
"""
import datetime
import re
try:
    import legifrance
except Exception:
    legifrance = None

# Les appels à PISTE passent par `legifrance._post`, qui réessaie lui-même les erreurs passagères
# (429, 5xx, réseau) et remonte aussitôt les erreurs définitives (400, 403...) : pas de second
# mécanisme de réessai ici.


def _clean(html):
    """Texte lisible d'un champ HTML de PISTE (travaux préparatoires, exposé des motifs, nota) :
    un alinéa par ligne, entités décodées (« &#233; » -> « é », « &nbsp; » -> espace).
    Repose sur `legifrance.alineas_de_html`, qui traite de même le texte des articles."""
    return "\n".join(legifrance.alineas_de_html(html))


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


_MESSAGE_PANNE = "PISTE n'a pas répondu : recherche inaboutie, à relancer."

# Textes créateurs dont les travaux propres n'éclairent pas, ou peu, l'intention du législateur :
# l'outil le dit et indique où chercher (il ne cherche pas lui-même ces autres textes).
_AVERTISSEMENT_ORDONNANCE = (
    "Version issue d'une ordonnance : pas de débats parlementaires sur ce texte. À consulter : "
    "le rapport au Président de la République publié avec l'ordonnance, la loi d'habilitation et "
    "ses travaux, et, s'il y a lieu, la loi de ratification et ses travaux. Le champ `ordonnance` "
    "donne ceux que Légifrance indique ; les lois d'habilitation y sont des candidates, tirées des "
    "visas, à vérifier.")
_AVERTISSEMENT_CODIFICATION = (
    "Le titre de ce texte évoque une codification : si elle est à droit constant, l'intention du "
    "législateur se trouve dans les travaux de la loi d'origine des dispositions codifiées.")
# Indice seulement : rien dans les données ne dit qu'une codification est à droit constant.
_RE_CODIFICATION = re.compile(r"partie législative|codification", re.IGNORECASE)

_RATIONE_TEMPORIS = "Texte ayant créé la version applicable au litige (non la rédaction actuelle)."
_RATIONE_TEMPORIS_PLUSIEURS = ("Textes ayant produit la version applicable au litige (non la "
                               "rédaction actuelle).")
_AVERTISSEMENT_ORIGINE = (
    "Version insérée dans le code par codification : les textes renvoyés sont ceux de la "
    "disposition codifiée (voir `codification`). Leurs travaux éclairent l'intention du "
    "législateur si la codification s'est faite à droit constant.")
_AVERTISSEMENT_DOSSIERS = (
    "Plusieurs dossiers législatifs sont rattachés à ce texte et aucun ne porte son intitulé : "
    "ils sont listés dans `autres_dossiers`, sans leurs pièces, à ouvrir un à un.")
_AVERTISSEMENT_PLUSIEURS = (
    "Plusieurs textes ont modifié cette version, et Légifrance ne dit pas lequel a produit la "
    "rédaction en cause : ils sont tous dans `textes`, chacun avec ses travaux, à vérifier un à un.")


def _avertissements(nature, titre):
    """Avertissements sur le texte créateur de la version, d'après sa nature et son titre :
    ordonnance (nature ORDONNANCE, ou titre commençant par « Ordonnance ») ; codification (titre
    évoquant la « partie législative » d'un code ou une « codification »). Liste, vide si aucun."""
    nature, titre = (nature or "").strip().upper(), (titre or "").strip()
    out = []
    if nature == "ORDONNANCE" or titre.lower().startswith("ordonnance"):
        out.append(_AVERTISSEMENT_ORDONNANCE)
    if _RE_CODIFICATION.search(titre):
        out.append(_AVERTISSEMENT_CODIFICATION)
    return out


def _date_valide(date):
    """Vrai si <date> est une date réelle au format AAAA-MM-JJ, celui qu'attend legifrance.py
    (même règle que `legifrance._ms`) : « 2024-03-15 » oui ; « 15/03/2024 », « 2024-02-30 »,
    une chaîne vide ou None, non."""
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def travaux_pour_article(code, article, date):
    """Retourne les travaux parlementaires du texte ayant créé la version de
    <article> du <code> applicable au <date> (YYYY-MM-DD).
    Les textes qui ont produit la version sont dans `textes`, chacun avec ses travaux (voir
    `_travaux_du_texte`). Quand il n'y en a qu'un, ses champs sont aussi au premier niveau de la
    réponse (`loi`, `lien_texte`, `lien_dossier`, `travaux_preparatoires`, `pieces`,
    `expose_motif`). Quand il y en a plusieurs, ils ne sont pas départagés : ces champs sont absents
    du premier niveau, et `avertissement` le signale.
    Pour une version insérée dans le code par codification, les textes sont ceux de la disposition
    codifiée (voir `legifrance.textes_produisant`) : la réponse porte alors `codification`, qui
    nomme le texte de codification et la disposition d'origine, et un `avertissement`.
    Une date invalide est refusée d'emblée : `trouve` False, `date_invalide` True, et un message
    qui rappelle le format attendu ; PISTE n'est pas interrogé.
    Si le texte créateur est une ordonnance ou semble être une codification, la réponse porte un
    `avertissement` qui dit où chercher l'intention du législateur (voir `_avertissements`).
    Si PISTE n'a pas répondu, la réponse porte `panne` (le message de l'incident), comme celles
    de legifrance.py : avec `trouve` False si l'article ou son texte créateur n'ont pu être
    identifiés ; avec `trouve` True si seuls les travaux ou le dossier n'ont pu être lus."""
    if not legifrance:
        return {"trouve": False, "erreur": "connecteur Légifrance indisponible"}
    if not _date_valide(date):
        return {"trouve": False, "date_invalide": True, "article": article, "code": code,
                "message": f"Date invalide : « {date} ». Format attendu : AAAA-MM-JJ (ex. 2024-03-15)."}
    if _est_reglementaire(article):
        return {"trouve": False, "reglementaire": True, "article": article, "code": code,
                "message": "Disposition réglementaire : pas de travaux parlementaires."}
    # exact=True : un autre article que celui demandé (« L. 181-18 » pour « L. 181-18-1 ») est
    # écarté par legifrance.py, qui renvoie alors `exact` False, et le `num` et le `lien` du plus proche.
    try:
        r = legifrance.resoudre(code, article, date, exact=True)
    except Exception as e:
        return {"trouve": False, "article": article, "code": code,
                "panne": legifrance._panne(e), "message": _MESSAGE_PANNE}
    if not r.get("trouve"):
        if r.get("panne"):
            return {"trouve": False, "article": article, "code": code,
                    "panne": r["panne"], "message": _MESSAGE_PANNE}
        if r.get("exact") is False:
            return {"trouve": False, "exact": False, "article": article, "code": code,
                    "num": r.get("num"), "lien": r.get("lien"),
                    "message": f"Article introuvable à cette date ; l'article le plus proche est {r.get('num')}."}
        return {"trouve": False, "article": article, "code": code,
                "message": "Version de l'article non résolue à cette date."}
    version = f'{r.get("version_debut")} → {r.get("version_fin") or "en cours"}'
    try:
        art = legifrance._post("/consult/getArticle", {"id": r["id"]}).get("article", {})
    except Exception as e:
        return {"trouve": False, "article": article, "code": code, "version": version,
                "panne": legifrance._panne(e), "message": _MESSAGE_PANNE}
    try:
        liens, codification = legifrance.textes_produisant(art)
    except Exception as e:
        # l'origine d'un article codifié n'a pu être lue : les références de codification restent
        liens, codification = legifrance.textes_de_version(art.get("lienModifications")), None
        panne_origine = legifrance._panne(e)
    else:
        panne_origine = None
    if not liens:
        return {"trouve": False, "article": article, "code": code, "version": version,
                "message": "Texte créateur de la version non identifié."}
    textes, panne = [], panne_origine
    for lien in liens:
        texte, p = _travaux_du_texte(lien)
        textes.append(texte)
        panne = panne or p
    reponse = {"trouve": True, "article": article, "code": code, "version": version,
               "textes": textes, "nota": _clean(art.get("nota")),
               "ratione_temporis": _RATIONE_TEMPORIS}
    if len(textes) == 1:
        reponse.update(textes[0])        # avec, s'il y a lieu, l'avertissement propre au texte
    else:
        reponse["ratione_temporis"] = _RATIONE_TEMPORIS_PLUSIEURS
    if codification:
        reponse["codification"] = codification
    avertissements = [a for a in ((_AVERTISSEMENT_ORIGINE if codification else None),
                                  (_AVERTISSEMENT_PLUSIEURS if len(textes) > 1 else None),
                                  reponse.get("avertissement")) if a]
    if avertissements:
        reponse["avertissement"] = " ".join(avertissements)
    if panne:
        reponse["panne"] = panne
    return reponse


def _travaux_du_texte(lien):
    """Travaux d'un texte qui a produit la version, désigné par un lien de modification.
    Renvoie (texte, panne) : `texte` porte `loi`, `lien_texte`, `lien_dossier`,
    `travaux_preparatoires`, `pieces`, `expose_motif` et, s'il y a lieu, `avertissement` ;
    `panne` est le message de l'incident si PISTE n'a pas répondu, None sinon."""
    cid = lien["textCid"]
    doss_id, prep, panne, visa = None, "", None, ""
    nature, titre = lien.get("natureText"), lien.get("textTitle")
    try:
        js = legifrance._post("/consult/jorf", {"textCid": cid})
        visa = js.get("visa") or ""
        nature = js.get("nature") or nature
        titre = js.get("title") or titre
        prep = _clean(js.get("prepWork"))
        dl = js.get("dossiersLegislatifs") or []
    except Exception as e:
        panne, dl = legifrance._panne(e), []
    propre, autres = _dossier_du_texte(dl, titre)
    doss_id = (propre or {}).get("id")
    dp = dossier_pieces(doss_id) if doss_id else {"pieces": [], "expose_motif": None}
    texte = {"loi": {"titre": titre, "nature": nature, "cid": cid,
                     "date_publi": lien.get("datePubliTexte")},
             "lien_texte": _lien_texte(cid),
             "lien_dossier": _lien_dossier(doss_id),
             "travaux_preparatoires": prep,
             "pieces": dp.get("pieces", []),
             "expose_motif": dp.get("expose_motif")}
    if dp.get("pieces_tronquees"):
        texte.update(pieces_tronquees=True, nombre_pieces=dp["nombre_pieces"])
    if autres:
        texte["autres_dossiers"] = [{"titre": re.sub(r"\s+", " ", d.get("titre") or "").strip(),
                                     "lien": _lien_dossier(d.get("id"))} for d in autres]
    if _est_ordonnance(nature, titre):
        texte["ordonnance"], p = _textes_de_l_ordonnance(visa, dp.get("pieces", []))
        panne = panne or p
    avertissements = _avertissements(nature, titre)
    if autres and not propre:
        avertissements.append(_AVERTISSEMENT_DOSSIERS)
    if avertissements:
        texte["avertissement"] = " ".join(avertissements)
    return texte, panne or dp.get("panne")


def _est_ordonnance(nature, titre):
    return (nature or "").strip().upper() == "ORDONNANCE" or (titre or "").strip().lower().startswith("ordonnance")


# Visa d'une loi citée pour certains de ses articles : « Vu la loi n° 2015-990 du 6 août 2015 pour
# la croissance [...], notamment ses articles 103 et 106 ».
_RE_VISA_LOI = re.compile(
    r"Vu\s+(la\s+loi\s+(?:organique\s+)?n[°º]\s*(\d{2,4}-\d+)([^;]*?)),\s*notamment\s+([^;]+)", re.I)
_RE_DATE_TEXTE = re.compile(r"du\s+(\d{1,2}(?:er)?\s+\w+\s+\d{4})", re.I)


def _textes_de_l_ordonnance(visa, pieces):
    """Textes à consulter pour une ordonnance, faute de débats parlementaires sur elle-même.
    `visa` : visas de l'ordonnance (HTML de /consult/jorf) ; `pieces` : pièces de son dossier
    législatif. Renvoie (ordonnance, panne).

    `ordonnance` porte, quand Légifrance les indique :
    - `rapport_au_president` et `ratification` : pris dans les textes du dossier de l'ordonnance,
      qui les donnent régulièrement (constaté le 02/11/2026 sur 10 ordonnances : « Rapport au
      Président de la République relatif à l'ordonnance [...] », « LOI n° 2018-148 [...] ratifiant
      l'ordonnance [...] » ou « Ordonnance ratifiée par l'article 56-III de la loi n° 2018-727 »);
    - `habilitation` : les lois que les visas citent pour certains de leurs articles (« notamment
      son article 106 »), sans hiérarchie. Les visas citent aussi d'autres lois, et parfois plus
      d'une ainsi : pour l'ordonnance n° 2017-80, la loi n° 74-696 (article 23) et la loi
      n° 2015-990 (articles 103 et 106). Une loi que le rapport au Président désigne comme loi
      d'habilitation porte `designee_par_le_rapport` True : une phrase du rapport évoque
      l'habilitation et donne son numéro, sa date (« l'article 103 de la loi du 6 août 2015
      susmentionné habilite le Gouvernement [...] ») ou un article que les visas citent pour elle
      (« l'article 8 de la loi d'habilitation », ordonnance n° 2016-131)."""
    ordonnance, panne = {}, None
    rapport = [p for p in pieces if (p.get("libelle") or "").lower().startswith("rapport au président")]
    if rapport:
        ordonnance["rapport_au_president"] = {"titre": rapport[0]["libelle"], "lien": rapport[0]["lien"]}
    ratif = [p for p in pieces if p.get("categorie") == "Textes du dossier"
             and re.search(r"ratifi", p.get("libelle") or "", re.I)]
    if ratif:
        ordonnance["ratification"] = [{"titre": p["libelle"], "lien": p["lien"]} for p in ratif]
    visas = re.sub(r"\s+", " ", " ".join(_clean(visa).split("\n")))
    candidats = []
    for m in _RE_VISA_LOI.finditer(visas):
        if m.group(2) not in [c["numero"] for c in candidats]:
            candidats.append({"loi": m.group(1).strip(), "numero": m.group(2),
                              "articles": m.group(4).strip().rstrip("."), "designee_par_le_rapport": False})
    if candidats and rapport:
        cid = rapport[0]["lien"].rstrip("/").rsplit("/", 1)[-1]
        try:
            phrases = [ph for ph in re.split(r"(?<=[.;])\s+", _texte_complet(cid)) if re.search(r"habilit", ph, re.I)]
        except Exception as e:
            phrases, panne = [], legifrance._panne(e)
        for c in candidats:
            date = _RE_DATE_TEXTE.search(c["loi"])
            reperes = [c["numero"]] + ([date.group(1)] if date else [])
            articles = [r"\barticle\s+%s\b" % n for n in re.findall(r"\d+", c["articles"])]
            c["designee_par_le_rapport"] = any(
                r in ph for ph in phrases for r in reperes) or any(
                re.search(a, ph) for ph in phrases for a in articles)
    for c in candidats:
        try:
            c["lien"] = legifrance.lien_loi(c["numero"])
        except Exception as e:
            c["lien"], panne = None, panne or legifrance._panne(e)
    if candidats:
        ordonnance["habilitation"] = candidats
    return ordonnance, panne


def _texte_complet(cid):
    """Texte d'un texte du Journal officiel (visas et articles), en une chaîne."""
    js = legifrance._post("/consult/jorf", {"textCid": cid})
    morceaux = [js.get("visa") or ""]
    for a in js.get("articles") or []:
        morceaux.append(a.get("content") or a.get("texte") or "")
    for sec in js.get("sections") or []:
        for a in sec.get("articles") or []:
            morceaux.append(a.get("content") or "")
    return re.sub(r"\s+", " ", " ".join(_clean(m) for m in morceaux))


_RE_NUMERO_TEXTE = re.compile(r"n[°º]\s*(\d{2,4}-\d+)")


def _dossier_du_texte(dossiers, titre):
    """Le dossier législatif propre au texte, parmi ceux que Légifrance lui rattache, et les autres.
    Renvoie (propre, autres) ; `propre` vaut None si aucun dossier n'est le sien.

    Une loi qui ratifie des ordonnances est aussi rattachée à leurs dossiers, et l'ordre de la
    liste ne met pas le sien en premier : pour la loi n° 2016-1087, le premier dossier est celui
    de l'ordonnance n° 2012-9 (constaté le 02/11/2026 ; de même pour les lois n° 2018-148 et
    n° 2024-322). Le dossier propre est celui dont l'intitulé porte le numéro du texte ; à
    défaut de numéro, celui dont l'intitulé est celui du texte. Si aucun ne correspond, un
    dossier seul est retenu ; plusieurs ne sont pas départagés."""
    dossiers = [d for d in (dossiers or []) if d.get("id")]
    m = _RE_NUMERO_TEXTE.search(titre or "")
    if m:
        siens = [d for d in dossiers
                 if (_RE_NUMERO_TEXTE.search(d.get("titre") or "") or [None, None])[1] == m.group(1)]
    else:
        voulu = _intitule(titre)
        siens = [d for d in dossiers if voulu and _intitule(d.get("titre")) == voulu]
    if siens:
        return siens[0], [d for d in dossiers if d is not siens[0]]
    if len(dossiers) == 1:
        return dossiers[0], []
    return None, dossiers


def _intitule(titre):
    """Intitulé comparable : sans renvoi de note final (« (1) »), espaces réduits, casse et
    accents repliés."""
    t = re.sub(r"\s*\(\d+\)\s*$", "", titre or "")
    return legifrance._fold(re.sub(r"\s+", " ", t)).strip()


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

def dossier_pieces(dole_id, max_pieces=None):
    """Consulte un dossier législatif (JORFDOLE) et renvoie ses pièces avec liens
    (projet de loi, rapports, débats, exposé des motifs...) + l'exposé des motifs.
    Toutes les pièces sont renvoyées, sauf si `max_pieces` est donné : la réponse porte alors
    `pieces_tronquees` True et `nombre_pieces`, le nombre total, quand la liste a été coupée.
    Les débats viennent en fin de liste : une coupe à 40, longtemps la règle, les retirait du
    dossier de la loi n° 2016-1087, qui compte 52 pièces (constaté le 02/11/2026).
    Si PISTE n'a pas répondu, la réponse porte `panne` (le message de l'incident)."""
    if not legifrance or not dole_id:
        return {"pieces": [], "expose_motif": None}
    try:
        d = legifrance._post("/consult/dossierLegislatif", {"id": dole_id}).get("dossierLegislatif", {})
    except Exception as e:
        return {"pieces": [], "expose_motif": None, "panne": legifrance._panne(e)}
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
    reponse = {"pieces": uniq, "expose_motif": _clean(d.get("exposeMotif"))}
    if max_pieces is not None and len(uniq) > max_pieces:
        reponse.update(pieces=uniq[:max_pieces], pieces_tronquees=True, nombre_pieces=len(uniq))
    return reponse


# Démonstration, exécutée seulement au lancement direct (`python travaux.py`).
# À GARDER EN FIN DE FICHIER : Python exécute le fichier de haut en bas, et une fonction définie plus
# bas n'existerait pas encore au moment de la démonstration (vérifié par test_travaux.py).
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
