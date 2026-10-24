#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Connecteur Légifrance via l'API PISTE (DILA).
Résout un article de code dans sa VERSION EN VIGUEUR à une date donnée
(en excès de pouvoir : date de l'acte attaqué), et renvoie texte + dates de
validité + lien Légifrance. Identifiants OAuth lus en local, jamais transmis.

Identifiants : variables d'environnement PISTE_CLIENT_ID / PISTE_CLIENT_SECRET,
ou fichier JSON {"client_id": "...", "client_secret": "..."} dont le chemin est
donné par PISTE_CREDENTIALS (par défaut ~/.piste.json). Ils ne sont transmis qu'à
oauth.piste.gouv.fr, jamais ailleurs.

Compte PISTE et abonnement à l'API Légifrance : https://piste.gouv.fr/
"""
import os, json, re, datetime, urllib.parse, urllib.request, unicodedata

OAUTH = "https://oauth.piste.gouv.fr/api/oauth/token"
API = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

def _creds():
    cid = os.environ.get("PISTE_CLIENT_ID"); cs = os.environ.get("PISTE_CLIENT_SECRET")
    if cid and cs:
        return cid, cs
    p = os.path.expanduser(os.environ.get("PISTE_CREDENTIALS", "~/.piste.json"))
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        return d.get("client_id"), d.get("client_secret")
    return None, None

_TOKEN = {"val": None, "exp": 0}
def token():
    import time
    if _TOKEN["val"] and time.time() < _TOKEN["exp"] - 30:
        return _TOKEN["val"]
    cid, cs = _creds()
    if not cid:
        raise RuntimeError("Identifiants PISTE absents (env PISTE_CLIENT_ID/SECRET, ou fichier JSON désigné par PISTE_CREDENTIALS, par défaut ~/.piste.json).")
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid,
                                   "client_secret": cs, "scope": "openid"}).encode()
    req = urllib.request.Request(OAUTH, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        js = json.loads(r.read())
    _TOKEN["val"] = js["access_token"]; _TOKEN["exp"] = time.time() + js.get("expires_in", 3600)
    return _TOKEN["val"]

def _post(path, payload, essais=4):
    """Appel PISTE. RÉESSAYÉ sur limitation de débit (HTTP 429) ou erreur passagère (5xx,
    réseau) : PISTE rationne les appels, et une rafale (une recherche par notion, par article
    proposé, par relâchement de termes) se voit refuser une partie de ses requêtes. Sans
    réessai, ces refus devenaient silencieusement des « article non trouvé » : le 07/09/2026,
    le banc a ainsi manqué l'article 225-5 du code pénal que le même appel, isolé, rendait."""
    import time as _t
    derniere = None
    for i in range(essais):
        req = urllib.request.Request(API + path, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            derniere = e
            if e.code == 401 and i == 0:
                _TOKEN["val"] = None            # jeton expiré : on en reprend un
            elif e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            derniere = e
        if i < essais - 1:
            _t.sleep(1.0 * (2 ** i))
    STATS["refus"] = STATS.get("refus", 0) + 1
    raise derniere

STATS = {}

# ==================================================================================================
# UNE PANNE N'EST PAS UN RÉSULTAT VIDE.
#
# Les fonctions de ce module rattrapaient toute exception et rendaient « pas trouvé ». Une clé PISTE
# absente ou expirée produisait donc exactement le même affichage qu'un article inexistant : « lien
# Légifrance indisponible », partout, sans un mot d'explication. Le 31/08/2026, cela m'a fait
# annoncer au rapporteur que la loi n° 2004-575 ne se résolvait pas — elle se résolvait très bien,
# c'était mon essai qui tournait sans identifiants.
#
# On enregistre donc la dernière panne, et les fonctions la reportent dans leur réponse.
# ==================================================================================================
DERNIERE_PANNE = {"quand": None, "quoi": None, "nombre": 0}


def _panne(e):
    """Mémorise une panne technique et dit si elle relève de l'authentification.
    `nombre` compte les pannes : comparé avant et après un appel, il dit si une panne est
    survenue pendant cet appel, même dans la même seconde qu'une précédente."""
    import time as _t
    msg = str(e)[:300]
    DERNIERE_PANNE["quand"] = _t.strftime("%Y-%m-%d %H:%M:%S")
    DERNIERE_PANNE["quoi"] = msg
    DERNIERE_PANNE["nombre"] += 1
    return msg


def etat_connecteur():
    """Le connecteur est-il en état de répondre ? Sert au contrôle d'aptitude et aux bandeaux."""
    try:
        token()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "motif": _panne(e),
                "authentification": "Identifiants PISTE" in str(e) or "oauth" in str(e).lower()}


# --- alinéas ---------------------------------------------------------------------------------
# Le champ `texte` rendu par PISTE est APLATI : 584 caractères pour l'article L. 557-1 du code de
# l'environnement, sans un seul saut de ligne, alors que l'article compte un alinéa chapeau et
# quatre 1° à 4°. Le champ `texteHtml` du même article porte six balises <p> : la mise en forme
# existe à la source, nous lisions simplement le mauvais champ. On ne reconstitue donc RIEN — on
# lit les alinéas là où ils sont. (Mesuré le 31/08/2026.)
_RE_BLOC = re.compile(r"</?(?:p|br|div|li)[^>]*>", re.IGNORECASE)
_RE_BALISE = re.compile(r"<[^>]+>")


_RE_TABLE = re.compile(r"<table[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
_RE_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_RE_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)


def _tableau_en_lignes(m):
    """Rend un tableau HTML sous forme d'alinéas « | cellule | cellule | », un par ligne.

    LES TABLEAUX D'APPLICABILITÉ OUTRE-MER — les « compteurs Lifou » — étaient jusqu'ici
    détruits : les balises étaient retirées sans rien mettre à la place, et les quarante-cinq
    lignes de l'article L. 783-2 du code monétaire et financier formaient un seul alinéa de
    2 927 caractères où les cellules se touchaient (« Articles applicablesDans leur rédaction
    résultant deL. 612-1… »). Aucune ligne n'y était comptable : « la huitième ligne du
    tableau » ne désignait rien, et le projet ne pouvait pas y être appliqué.
    """
    import html as _h
    lignes = []
    for tr in _RE_TR.findall(m.group(0)):
        cells = []
        for td in _RE_TD.findall(tr):
            t = _RE_BLOC.sub(" ", td)
            t = _RE_BALISE.sub("", t)
            t = _h.unescape(t)
            cells.append(re.sub(r"\s+", " ", t).strip())
        if any(cells):
            lignes.append("| " + " | ".join(cells) + " |")
    return "\n" + "\n".join(lignes) + "\n" if lignes else "\n"


def alineas_de_html(html):
    """Découpe un texte HTML Légifrance en alinéas, dans l'ordre, sans rien inventer.

    Les tableaux sont traités AVANT le retrait des balises : une ligne de tableau devient un
    alinéa « | cellule | cellule | », forme commune aux deux colonnes du tableau à trois
    colonnes (cf. le module `tableaux`)."""
    if not html:
        return []
    html = _RE_TABLE.sub(_tableau_en_lignes, html)
    brut = _RE_BLOC.sub("\n", html)
    brut = _RE_BALISE.sub("", brut)
    import html as _h
    brut = _h.unescape(brut)
    out = []
    for ligne in brut.split("\n"):
        t = re.sub(r"[ \t ]+", " ", ligne).strip()
        if t:
            out.append(t)
    return out


def _ms(date):  # 'YYYY-MM-DD' -> ms epoch
    return int(datetime.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)

def _iso(ms):
    if not ms: return None
    return datetime.datetime.utcfromtimestamp(ms/1000).strftime("%Y-%m-%d")


# ==================================================================================================
# DATE DE FIN « SANS TERME ».
#
# Légifrance ne laisse pas vide la date de fin d'une version en vigueur : il y inscrit le
# 1er janvier 2999, soit 32472144000000 ms. Constaté le 24/10/2026 sur les articles en vigueur du
# code civil (champ `dateFin` de toutes les versions à l'état VIGUEUR) et sur l'article L. 181-18 du
# code de l'environnement (« Date fin vigueur : 01/01/2999 »).
#
# Lue comme une vraie date, elle s'affichait : « 2023-03-12 → 2999-01-01 ». `_iso_fin` la rend None,
# ce qui veut dire « pas de fin » : travaux.py et la démonstration de ce module affichent alors
# « en cours », comme ils le prévoyaient.
#
# Toute date à partir du 1er janvier 2999 est traitée de même, au cas où Légifrance emploierait une
# variante (31/12/2999...). Une autre date conventionnelle, antérieure à 2999, ne serait PAS
# reconnue : aucune n'a été observée. Une vraie date de fin future (abrogation programmée au
# 1er janvier 2027, par exemple) est conservée.
# ==================================================================================================
_SANS_FIN_MS = 32472144000000          # 2999-01-01 00:00 UTC


def _iso_fin(ms):
    """Date de fin d'une version : None si elle est absente ou « sans terme » (voir ci-dessus)."""
    if ms and ms >= _SANS_FIN_MS:
        return None
    return _iso(ms)

def _find_ids(obj, acc):
    # parcours récursif pour récupérer les identifiants LEGIARTI
    if isinstance(obj, dict):
        i = obj.get("id") or obj.get("cid")
        if isinstance(i, str) and i.startswith("LEGIARTI"):
            acc.append(i)
        for v in obj.values():
            _find_ids(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _find_ids(v, acc)
    return acc

# Alias des codes usuels -> nom EXACT attendu par la facette NOM_CODE de Légifrance
_CODE_ALIAS = {
    "ceseda": "Code de l'entrée et du séjour des étrangers et du droit d'asile",
    "cgi": "Code général des impôts",
    "lpf": "Livre des procédures fiscales",
    "cja": "Code de justice administrative",
    "cgct": "Code général des collectivités territoriales",
    "csp": "Code de la santé publique",
    "css": "Code de la sécurité sociale",
    "code de l'urbanisme": "Code de l'urbanisme",
    "code de l'environnement": "Code de l'environnement",
    "code des relations entre le public et l'administration": "Code des relations entre le public et l'administration",
    "crpa": "Code des relations entre le public et l'administration",
}


def _fold(s):
    """Repli insensible aux accents / casse / apostrophes / espaces (pour comparer des noms de code)."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("’", "'").replace("ʼ", "'").replace(" ", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


_CODES_MAP = None   # {nom_plié: NOM_CODE canonique (accentué)}


def _cache_codes_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "codes_legifrance.json")


def _charger_codes():
    """Catalogue des noms officiels de codes (facette NOM_CODE), mis en cache localement.
    Sert à retrouver le nom canonique accentué à partir d'une saisie sans accents."""
    global _CODES_MAP
    if _CODES_MAP is not None:
        return _CODES_MAP
    noms = []
    p = _cache_codes_path()
    if os.path.exists(p):
        try:
            noms = json.load(open(p, encoding="utf-8"))
        except Exception:
            noms = []
    if not noms:
        try:
            js = _post("/list/code", {"pageSize": 300, "pageNumber": 1, "states": ["VIGUEUR", "ABROGE"]})
            noms = sorted({(r.get("titre") or "").strip() for r in (js.get("results") or []) if r.get("titre")})
            if noms:
                try:
                    json.dump(noms, open(p, "w", encoding="utf-8"), ensure_ascii=False)
                except Exception:
                    pass
        except Exception:
            noms = []
    _CODES_MAP = {_fold(n): n for n in noms}
    return _CODES_MAP


def code_connu(nom):
    """Le nom donné est-il celui d'un code EXISTANT ? Renvoie le nom officiel, ou "".

    POURQUOI CETTE FONCTION. La résolution des liens d'un projet essaie chaque article contre
    chaque « code » repéré dans le texte. Or la règle qui repère les codes part du mot « code » et
    prend la suite de la phrase : elle produit donc, à côté des vrais intitulés, des choses comme
    « codes informatiques et de données », « codes et lois relatifs à », « code des ». Chacune
    partait ensuite en requête vers Légifrance, à une seconde pièce — mesuré le 31/08/2026 : le
    travail se comptait en heures et le rapporteur voyait un compteur qui ne bougeait plus.

    Un nom qui n'est pas un code NE PEUT PAS résoudre : l'interroger est du temps perdu, pas une
    chance à tenter. On confronte donc au catalogue officiel (108 intitulés, en cache local), sans
    aucun appel réseau. Ce qui n'y figure pas reste dans le texte, simplement non résolu."""
    c = (nom or "").strip()
    if not c:
        return ""
    c = _CODE_ALIAS.get(c.lower(), c)
    try:
        return _charger_codes().get(_fold(c), "")
    except Exception:
        return ""


def _canon_code(code):
    c = (code or "").strip()
    c = _CODE_ALIAS.get(c.lower(), c)
    # repli insensible aux accents : retrouver le nom officiel exact (facette NOM_CODE accentuée)
    try:
        m = _charger_codes()
        canon = m.get(_fold(c))
        if canon:
            return canon
    except Exception:
        pass
    if c[:1].islower():   # « livre des procédures fiscales » -> « Livre des procédures fiscales » (casse NOM_CODE)
        c = c[0].upper() + c[1:]
    return c


# « article », « Article », « articles », « art. », « Art. », « l'article » en tête d'une désignation
_RE_PREFIXE_ARTICLE = re.compile(r"^\s*(?:l['’]\s*)?art(?:icle)?s?\.?\s*", re.IGNORECASE)


def _art_candidates(article):
    """Du plus spécifique au plus général : retire le mot « article » ou « art. » en tête, les
    alinéas (« 8° », « a) ») et, en cascade, les subdivisions terminales séparées par un tiret
    (ex. CGI 158-5-a -> 158).
    « L. 314-11 8° » -> ['L314-11', 'L314'] ; « 158-5-a » -> ['158-5-a','158-5','158'] ;
    « Article L. 181-18 » -> ['L181-18', 'L181'] ; « article 6 » -> ['6']."""
    a = _RE_PREFIXE_ARTICLE.sub("", article or "")      # retire « article », « art. »
    a = re.sub(r"\s*\d+\s*°.*$", "", a)                  # retire « 8° … »
    a = re.sub(r"\s*[a-zA-Z]\s*\)\s*$", "", a)          # retire « a) »
    core = re.sub(r"[\s.]", "", a.strip())                # « L. 314-11 » -> « L314-11 »
    bases = [core] if core else []
    while "-" in core:
        core = core.rsplit("-", 1)[0]
        if core and core not in bases:
            bases.append(core)
    cands = []
    for b in bases:
        cands.append(b)
        m = re.match(r"^([LRD]?\d[\d-]*)([A-Z])$", b)         # « L54A » : Légifrance écrit « L54 A »
        if m:
            cands.append(m.group(1) + " " + m.group(2))
        m = re.match(r"^([RD])(\d.*)$", b, re.I)          # article réglementaire -> variante astérisque (CGI, LPF)
        if m:
            star = m.group(1) + "*" + m.group(2)
            if star not in cands:
                cands.append(star)
    return cands


def _meme_article(demande, rendu):
    """Deux écritures d'un même numéro d'article (« L. 321-3 » et « L321-3 ») désignent-elles le
    même article ? Comparaison sur la forme canonique, sans « article » ou « art. » en tête,
    sans espaces ni points, alinéas retirés."""
    def canon(x):
        x = _RE_PREFIXE_ARTICLE.sub("", str(x or ""))       # « article », « art. »
        x = re.sub(r"\s*\d+\s*°.*$", "", x)                 # « 8° … »
        x = re.sub(r"\s*[a-zA-Z]\s*\)\s*$", "", x)          # « a) »
        return re.sub(r"[\s.‑]", "", x).strip().lower()
    return bool(canon(demande)) and canon(demande) == canon(rendu)


_RE_NUM_LOI = re.compile(r"n[°º]\s*(\d{2,4}[-‑]\d+)")


def _articles_de_loda(obj, acc):
    """Tous les articles portés par la structure d'un texte LODA, à plat."""
    if isinstance(obj, dict):
        if obj.get("num") and (obj.get("content") or obj.get("texte") or obj.get("texteHtml")):
            acc.append(obj)
        for v in obj.values():
            _articles_de_loda(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _articles_de_loda(v, acc)
    return acc


def _ecarter_inexact(r):
    """`r` : la réponse de `resoudre` ou de `resoudre_loi`.
    Remplace un résultat trouvé mais INEXACT (la cascade a rendu un autre article que celui
    demandé) par un refus : `trouve` False, `exact` False, et le `num` et le `lien` de l'article
    le plus proche. Tout autre résultat est rendu tel quel."""
    if r.get("trouve") and not r.get("exact", True):
        return {"code": r.get("code"), "article": r.get("article"), "date": r.get("date_demandee"),
                "trouve": False, "exact": False, "num": r.get("num"), "lien": r.get("lien"),
                "brut": None}
    return r


def resoudre_loi(nom, article, date, exact=False):
    """L'article d'une LOI (ou ordonnance, ou décret), et non d'un code.
    Avec exact=True, un article autre que celui demandé est écarté (voir `_ecarter_inexact`).
    Si PISTE n'a pas répondu, la réponse porte `panne` (le message de l'incident).

    LE CONNECTEUR NE SAVAIT RÉSOUDRE QUE LES ARTICLES DE CODE. `resoudre` interroge le fonds
    CODE_DATE avec la facette NOM_CODE : par construction, un article de LOI n'y est jamais
    trouvé. Le tableau affichait donc « L'article 108 n'a pas été trouvé dans la loi n° 86-1067
    du 30 septembre 1986 : vérifier le droit en vigueur dans Légifrance » — pour un article qui
    existe et que Légifrance sert très bien —, laissait la colonne du droit en vigueur vide, et
    ne pouvait évidemment rien consolider. Cela valait pour TOUTE loi : loi de 1986, loi de 1978
    sur l'informatique et les libertés, loi de 2004 pour la confiance dans l'économie numérique.
    Relevé le 01/09/2026. On passe donc par le fonds LODA : le texte est identifié par son
    numéro, son plan est demandé une fois, et l'article y est cherché par son numéro.
    """
    m = _RE_NUM_LOI.search(nom or "")
    if not m:
        return {"code": nom, "article": article, "date": date, "trouve": False, "brut": None}
    pannes_avant = DERNIERE_PANNE["nombre"]
    tid, titre = _legitext_loi(m.group(1).replace("‑", "-"))
    if not tid:
        refus = {"code": nom, "article": article, "date": date, "trouve": False, "brut": None}
        if DERNIERE_PANNE["nombre"] != pannes_avant:      # loi non identifiée faute de réponse
            refus["panne"] = DERNIERE_PANNE["quoi"]
        return refus
    ck = (tid, _ms(date))
    r = _TOC_CACHE.get(ck)
    if r is None:
        try:
            r = _post("/consult/legiPart", {"textId": tid, "date": _ms(date)})
        except Exception as e:
            return {"code": nom, "article": article, "date": date, "trouve": False, "brut": None,
                    "panne": _panne(e)}
        if len(_TOC_CACHE) > 40:
            _TOC_CACHE.clear()
        _TOC_CACHE[ck] = r
    voulus = [_fold(x) for x in _art_candidates(article)]
    for a in _articles_de_loda(r, []):
        if _fold(str(a.get("num") or "")) in voulus:
            html = a.get("content") or a.get("texteHtml") or ""
            aid = a.get("id") or a.get("cid") or ""
            # L'ARTICLE RENDU EST-IL BIEN CELUI DEMANDÉ ? La recherche procède en cascade, du plus
            # spécifique au plus général : « 55-1 » n'existant pas — le projet le crée — elle
            # retombait sur l'article « 55 » et je le donnais pour exact. Le tableau affichait
            # alors, en regard d'un article que le projet institue, le texte d'un tout autre
            # article de la même loi — faux, et parfaitement plausible. Régression du 01/09/2026,
            # relevée par le rapporteur sur les articles 55-1 à 55-6 de la loi n° 2004-575. On
            # compare donc le numéro rendu au numéro demandé, comme le fait déjà `resoudre` pour
            # les codes, et l'appelant écarte ce qui n'est pas exact.
            est_exact = _meme_article(article, a.get("num"))
            r = {
                "code": titre or nom, "article": article, "date_demandee": date, "trouve": True,
                "exact": est_exact, "id": aid, "num": a.get("num"),
                "alineas": alineas_de_html(html),
                "texte": re.sub(r"<[^>]+>", " ", html).strip(),
                "version_debut": _iso(a.get("dateDebut")), "version_fin": _iso_fin(a.get("dateFin")),
                "lien": ("https://www.legifrance.gouv.fr/loda/article_lc/%s" % aid) if aid
                        else ("https://www.legifrance.gouv.fr/loda/id/%s" % tid),
            }
            return _ecarter_inexact(r) if exact else r
    return {"code": nom, "article": article, "date": date, "trouve": False, "brut": None}


def resoudre(code, article, date, exact=False):
    """Retourne l'article de <code> portant le n° <article>, dans sa version au <date>.
    Tolère les alias de codes (CESEDA, CGI, LPF...), le mot « article » ou « art. » devant le
    numéro et les suffixes d'alinéa (« 8° »). `version_fin` vaut None pour une version sans
    terme, c'est-à-dire encore en vigueur (voir `_iso_fin`).

    Par défaut, un article autre que celui demandé, rendu par la cascade de `_art_candidates`,
    est renvoyé avec `exact` False ; c'est à l'appelant de l'écarter ou de le retenir (CGI :
    « 158-5-a » -> article 158). Avec exact=True, il est écarté ici (voir `_ecarter_inexact`).

    Si le texte visé n'est pas un code mais une LOI, la recherche est aiguillée vers le fonds
    LODA : les deux fonds sont distincts, et chercher un article de loi dans CODE_DATE ne rend
    jamais rien."""
    if not code_connu(code) and _RE_NUM_LOI.search(code or ""):
        return resoudre_loi(code, article, date, exact=exact)
    code = _canon_code(code)
    for num in _art_candidates(article):
        payload = {"recherche": {
            "champs": [{"typeChamp": "NUM_ARTICLE",
                        "criteres": [{"typeRecherche": "EXACTE", "valeur": num, "operateur": "ET"}],
                        "operateur": "ET"}],
            "filtres": [{"facette": "NOM_CODE", "valeurs": [code]},
                        {"facette": "DATE_VERSION", "singleDate": _ms(date)}],
            "pageNumber": 1, "pageSize": 5, "operateur": "ET", "sort": "PERTINENCE",
            "typePagination": "ARTICLE"}, "fond": "CODE_DATE"}
        res = _post("/search", payload)
        ids = _find_ids(res, [])
        if not ids:
            continue
        art = _post("/consult/getArticle", {"id": ids[0]}).get("article", {})
        # L'ARTICLE RENDU EST-IL BIEN CELUI DEMANDÉ ? La recherche procède en cascade, du plus
        # spécifique au plus général : « L. 321-3-2 » n'existant pas, elle renvoyait « L. 321-3 »
        # sans le dire, et le rapporteur cliquait sur un lien pointant vers un AUTRE article — le
        # cas se présente à chaque fois qu'un projet CRÉE des articles. On compare donc le numéro
        # rendu au numéro demandé, et l'écart est signalé par `exact`.
        est_exact = _meme_article(article, art.get("num"))
        r = {
            "code": code, "article": article, "date_demandee": date, "trouve": True,
            "exact": est_exact,
            "id": art.get("id") or ids[0],
            "num": art.get("num"),
            # LES ALINÉAS, pris de `texteHtml` : c'est la seule forme qui les porte. `texte` reste
            # rendu pour les usages qui n'ont besoin que d'une chaîne (recherche, embeddings).
            "alineas": alineas_de_html(art.get("texteHtml") or "") or (
                [(art.get("texte") or "").strip()] if (art.get("texte") or "").strip() else []),
            "texte": (art.get("texte") or "").strip(),
            "version_debut": _iso(art.get("dateDebut")),
            "version_fin": _iso_fin(art.get("dateFin")),
            "lien": f"https://www.legifrance.gouv.fr/codes/article_lc/{art.get('id') or ids[0]}",
        }
        return _ecarter_inexact(r) if exact else r
    return {"code": code, "article": article, "date": date, "trouve": False, "brut": None}


# ---------- jurisprudence constitutionnelle (fonds CONSTIT) ----------
def _lien_cc(titre):
    core = titre.split(" - ")[0].replace("Décision", "").strip()
    mnat = re.search(r"\b(QPC|DC|LOM|LP|FNR|L)\b", core)
    mnum = re.match(r"(\d{4})-([\d/]+)", core)
    if not (mnat and mnum):
        return core, None, None
    an, num = mnum.group(1), mnum.group(2).replace("/", "_")
    return core, mnat.group(1), f"https://www.conseil-constitutionnel.fr/decision/{an}/{an}{num}{mnat.group(1)}.htm"

def _url_ok(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
            return r.status == 200
    except Exception:
        return False

def chercher_constit(question, k=5, natures=("qpc", "dc")):
    """Recherche dans la jurisprudence du Conseil constitutionnel (fonds CONSTIT)."""
    payload = {"recherche": {"champs": [{"typeChamp": "ALL",
        "criteres": [{"typeRecherche": "UN_DES_MOTS", "valeur": question, "operateur": "ET"}],
        "operateur": "ET"}], "pageNumber": 1, "pageSize": 30, "operateur": "ET",
        "sort": "PERTINENCE", "typePagination": "DEFAUT"}, "fond": "CONSTIT"}
    js = _post("/search", payload)
    out = []
    for res in js.get("results", []):
        if res.get("nature") not in natures:
            continue
        titre = (res.get("titles") or [{}])[0].get("title", "")
        core, nat, lien = _lien_cc(titre)
        if not lien:
            continue
        extrait = re.sub(r"</?mark>", "", res.get("text") or "").strip()
        parties = " - ".join(titre.split(" - ")[1:]) if " - " in titre else ""
        out.append({"reference": f"Cons. const., déc. n° {core}", "intitule": parties[:160],
                    "solution": res.get("solution"), "extrait": extrait[:400], "lien": lien})
        if len(out) >= k:
            break
    return out


# ---------- recherche plein texte (textes législatifs/réglementaires) ----------
def _find_any_id(obj, prefixes=("LEGIARTI", "LEGITEXT", "JORFTEXT", "KALITEXT"), acc=None):
    if acc is None:
        acc = []
    if isinstance(obj, dict):
        i = obj.get("id") or obj.get("cid")
        if isinstance(i, str) and any(i.startswith(p) for p in prefixes):
            acc.append(i)
        for v in obj.values():
            _find_any_id(v, prefixes, acc)
    elif isinstance(obj, list):
        for v in obj:
            _find_any_id(v, prefixes, acc)
    return acc

def chercher_texte(question, k=5, fond="CODE_ETAT"):
    """Recherche plein texte dans Légifrance (fond CODE_ETAT par défaut ; LODA_ETAT pour lois/ordonnances).
    Retour : liste de {reference, extrait, lien, fond}."""
    payload = {"recherche": {"champs": [{"typeChamp": "ALL",
        "criteres": [{"typeRecherche": "UN_DES_MOTS", "valeur": question, "operateur": "ET"}],
        "operateur": "ET"}], "pageNumber": 1, "pageSize": max(1, min(k, 20)),
        "operateur": "ET", "sort": "PERTINENCE", "typePagination": "DEFAUT"}, "fond": fond}
    js = _post("/search", payload)
    out = []
    for res in (js.get("results") or []):
        secs = res.get("sections") or []
        if secs:
            for sec in secs:
                for ex in (sec.get("extracts") or []):
                    num = ex.get("num"); idd = ex.get("id")
                    vals = ex.get("values") or []
                    txt = " ".join(v for v in vals if isinstance(v, str))
                    txt = re.sub(r"</?mark>", "", txt); txt = re.sub(r"\s+", " ", txt).strip()
                    ref = f"Article {num}" if num else (sec.get("title") or "Texte")
                    lien = f"https://www.legifrance.gouv.fr/codes/article_lc/{idd}" if (idd and idd.startswith("LEGIARTI")) else None
                    out.append({"reference": ref, "extrait": txt[:300], "lien": lien, "fond": fond})
                    if len(out) >= k:
                        return out
        else:
            titre = (res.get("titles") or [{}])[0].get("title") or res.get("title") or "Texte"
            ids = _find_any_id(res); lien = None
            if ids:
                idd = ids[0]
                if idd.startswith("LEGIARTI"):
                    lien = f"https://www.legifrance.gouv.fr/codes/article_lc/{idd}"
                elif idd.startswith("JORFTEXT"):
                    lien = f"https://www.legifrance.gouv.fr/jorf/id/{idd}"
                elif idd.startswith("LEGITEXT"):
                    lien = f"https://www.legifrance.gouv.fr/loda/id/{idd}"
            out.append({"reference": (titre or "Texte").strip(), "extrait": "", "lien": lien, "fond": fond})
            if len(out) >= k:
                return out
    return out[:k]


def chercher_termes(termes, k=5, fond="CODE_ETAT"):
    """Recherche par TERMES SAILLANTS (tous présents dans un même champ), et non par la
    question entière en « un des mots ». Mesuré sur le banc manuel le 06/09/2026 : la
    question entière rendait du bruit (« Article 41 DE », « 6° : »), 2 sources sur 70.
    Retour : liste de {reference, titre, extrait, lien, fond}, la référence portant le
    NOM DU TEXTE (« Code de l'énergie, article L132-2 »), sans quoi deux articles L132-2
    de deux codes sont indiscernables."""
    valeur = " ".join(t for t in (termes or []) if t).strip()
    if not valeur:
        return []
    payload = {"recherche": {"champs": [{"typeChamp": "ALL",
        "criteres": [{"typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP", "valeur": valeur, "operateur": "ET"}],
        "operateur": "ET"}], "pageNumber": 1, "pageSize": max(1, min(k, 20)),
        "operateur": "ET", "sort": "PERTINENCE", "typePagination": "DEFAUT"}, "fond": fond}
    js = _post("/search", payload)
    out = []
    for res in (js.get("results") or []):
        titre = ((res.get("titles") or [{}])[0].get("title") or res.get("title") or "").strip()
        titre = re.sub(r"</?mark>", "", titre)
        secs = res.get("sections") or []
        if secs:
            for sec in secs:
                for ex in (sec.get("extracts") or []):
                    num = ex.get("num"); idd = ex.get("id")
                    vals = ex.get("values") or []
                    txt = " ".join(v for v in vals if isinstance(v, str))
                    txt = re.sub(r"</?mark>", "", txt); txt = re.sub(r"\s+", " ", txt).strip()
                    art = re.sub(r"</?mark>", "", f"article {num}" if num else (sec.get("title") or ""))
                    ref = ", ".join(x for x in (titre, art) if x) or "Texte"
                    lien = f"https://www.legifrance.gouv.fr/codes/article_lc/{idd}" if (idd and idd.startswith("LEGIARTI")) else None
                    out.append({"reference": ref, "titre": titre, "extrait": txt[:300], "lien": lien, "fond": fond})
                    if len(out) >= k:
                        return out
        else:
            ids = _find_any_id(res); lien = None
            if ids:
                idd = ids[0]
                if idd.startswith("LEGIARTI"):
                    lien = f"https://www.legifrance.gouv.fr/codes/article_lc/{idd}"
                elif idd.startswith("JORFTEXT"):
                    lien = f"https://www.legifrance.gouv.fr/jorf/id/{idd}"
                elif idd.startswith("LEGITEXT"):
                    lien = f"https://www.legifrance.gouv.fr/loda/id/{idd}"
            out.append({"reference": titre or "Texte", "titre": titre, "extrait": "", "lien": lien, "fond": fond})
            if len(out) >= k:
                return out
    return out[:k]


# ---------- résolution d'une SUBDIVISION (section/chapitre/titre/livre) -> lien Légifrance ----------
def _legitext_loi(num, natures=("LOI", "ORDONNANCE", "DECRET")):
    """LEGITEXT d'une loi/ordonnance/décret par son NUMÉRO exact (ex. « 2004-575 »)."""
    num = num.replace("‑", "-")
    payload = {"recherche": {"champs": [{"typeChamp": "NUM",
        "criteres": [{"typeRecherche": "EXACTE", "valeur": num, "operateur": "ET"}], "operateur": "ET"}],
        "pageNumber": 1, "pageSize": 10, "operateur": "ET", "sort": "PERTINENCE", "typePagination": "DEFAUT"},
        "fond": "LODA_DATE"}
    try:
        js = _post("/search", payload)
    except Exception as e:
        _panne(e)          # ne pas confondre « rien trouvé » et « je n'ai pas pu chercher »
        return None, ""
    for r in (js.get("results") or []):
        for t in (r.get("titles") or []):
            tid = t.get("id") or t.get("cid"); ti = t.get("title", "")
            if tid and tid.startswith("LEGITEXT") and num in (ti or ""):
                return re.sub(r"_.*", "", tid), ti
    ids = _find_any_id(js, ["LEGITEXT"])
    return (re.sub(r"_.*", "", ids[0]) if ids else None), ""


def _legitext_code(code):
    """LEGITEXT d'un code par son nom (facette NOM_CODE)."""
    canon = _canon_code(code)
    payload = {"recherche": {"champs": [{"typeChamp": "ALL",
        "criteres": [{"typeRecherche": "UN_DES_MOTS", "valeur": canon, "operateur": "ET"}], "operateur": "ET"}],
        "filtres": [{"facette": "NOM_CODE", "valeurs": [canon]}],
        "pageNumber": 1, "pageSize": 5, "operateur": "ET", "typePagination": "DEFAUT"}, "fond": "CODE_DATE"}
    try:
        js = _post("/search", payload)
    except Exception as e:
        _panne(e)          # ne pas confondre « rien trouvé » et « je n'ai pas pu chercher »
        return None
    ids = _find_any_id(js, ["LEGITEXT"])
    return re.sub(r"_.*", "", ids[0]) if ids else None


def _fold_lf(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(c))


_TYPES_SUBDIV = ("livre", "titre", "chapitre", "section", "sous-section", "paragraphe")


_RMAP = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman_to_int(s):
    val = prev = 0
    for ch in reversed(s):
        v = _RMAP.get(ch, 0)
        val += -v if v < prev else v
        prev = max(prev, v)
    return val


def _int_to_roman(n):
    out = ""
    for v, sym in [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                   (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]:
        while n >= v:
            out += sym; n -= v
    return out


def _split_num(x):
    x = _fold_lf(x).strip()
    m = re.match(r"([0-9]+|[ivxlcdm]+)(?:er|re|nd|eme|ere|e)?\s*(bis|ter|quater|quinquies)?", x)
    if not m:
        return x, ""
    return m.group(1), (m.group(2) or "")


def _num_eq(a, b):
    ca, sa = _split_num(a); cb, sb = _split_num(b)
    if sa != sb:
        return False
    if ca == cb:
        return True
    va = int(ca) if ca.isdigit() else _roman_to_int(ca)
    vb = int(cb) if cb.isdigit() else _roman_to_int(cb)
    return va and va == vb


def _match_subdiv(title, typ, num):
    n = _fold_lf(re.sub(r"\s+", " ", title)).split(":")[0].strip()
    if not n.startswith(typ + " "):
        return False
    label = n[len(typ) + 1:].strip()
    return _num_eq(label, num)


def _walk_toc(secs, chemin):
    typ, num = chemin[0]
    secs = secs or []
    # 1) correspondances directes au niveau courant
    for s in secs:
        if _match_subdiv(s.get("title", ""), typ, num):
            if len(chemin) == 1:
                return s
            hit = _walk_toc(s.get("sections") or [], chemin[1:])
            if hit:
                return hit
    # 2) descente TRANSPARENTE à travers les conteneurs « Partie … » des codes
    #    (Partie législative / réglementaire, Première/Deuxième partie…), législative d'abord.
    conteneurs = [s for s in secs if "partie" in _fold_lf(s.get("title", "")).split()[:2]]
    conteneurs.sort(key=lambda s: 0 if "legislative" in _fold_lf(s.get("title", "")) else 1)
    for s in conteneurs:
        hit = _walk_toc(s.get("sections") or [], chemin)
        if hit:
            return hit
    return None


_TOC_CACHE = {}     # {(text_id, date_ms): plan complet} — voir resoudre_subdivision


def resoudre_subdivision(parent_kind, parent_key, chemin, date=None):
    """Résout une subdivision (chemin = liste [(type, num)] du plus GÉNÉRAL au plus SPÉCIFIQUE,
    ex. [('titre','Ier'),('chapitre','II'),('section','3')]) d'un CODE (parent_kind='code',
    parent_key=nom du code) ou d'une LOI/ORDONNANCE (parent_kind='loi', parent_key=numéro).
    Renvoie {trouve, lien, titre}. Lien = page section_lc de Légifrance (codes/ ou loda/)."""
    if not chemin:
        return {"trouve": False}
    date = date or datetime.datetime.now().strftime("%Y-%m-%d")
    _av = DERNIERE_PANNE.get("nombre")
    if parent_kind == "code":
        tid = _legitext_code(parent_key); base = "codes"
    else:
        tid, _ti = _legitext_loi(parent_key); base = "loda"
    if not tid:
        # Le texte n'a pas été identifié : est-ce parce qu'il n'existe pas, ou parce que la
        # recherche a échoué ? On le dit, au lieu de laisser croire à une absence.
        if DERNIERE_PANNE.get("nombre") != _av:
            return {"trouve": False, "panne": DERNIERE_PANNE.get("quoi")}
        return {"trouve": False}
    # LA TABLE DES MATIÈRES D'UN CODE NE SE TÉLÉCHARGE QU'UNE FOIS.
    #
    # `legiPart` rend le plan COMPLET du code : de deux à quinze secondes selon sa taille (code de
    # la santé publique : 13,8 s, mesuré le 31/08/2026). Un projet qui cite deux subdivisions du
    # même code le téléchargeait deux fois, et le rapporteur attendait deux fois. Le plan ne
    # dépend que du texte et de la date : on le garde pour la durée du processus.
    ck = (tid, _ms(date))
    r = _TOC_CACHE.get(ck)
    if r is None:
        try:
            r = _post("/consult/legiPart", {"textId": tid, "date": _ms(date)})
        except Exception as e:
            return {"trouve": False, "panne": _panne(e)}
        if len(_TOC_CACHE) > 40:      # borne mémoire : un plan de code pèse plusieurs mégaoctets
            _TOC_CACHE.clear()
        _TOC_CACHE[ck] = r
    chem = [(_fold_lf(t), n) for (t, n) in chemin]
    hit = _walk_toc(r.get("sections") or [], chem)
    if not hit:
        return {"trouve": False, "text_id": tid}
    cid = hit.get("cid") or hit.get("id")
    if parent_kind == "code":
        # FORME COMPLÈTE : identifiant du code, identifiant de la section, puis l'ancre. La forme
        # abrégée `/section_lc/<LEGISCTA>` ouvrait la section hors de son code, sans le plan qui
        # l'entoure et sans positionner la page. Forme donnée par le rapporteur le 31/08/2026.
        lien = "https://www.legifrance.gouv.fr/codes/section_lc/%s/%s/#%s" % (tid, cid, cid)
    else:
        # loi/ordonnance : texte consolidé EN VIGUEUR (loda/id) + ancre vers la section
        lien = "https://www.legifrance.gouv.fr/loda/id/%s#%s" % (tid, cid)
    return {"trouve": True, "titre": hit.get("title"), "lien": lien, "text_id": tid, "cid": cid}


def lien_loi(num):
    """Lien vers le TEXTE ENTIER (version consolidée en vigueur) d'une loi/ordonnance/décret numéroté."""
    tid, _ti = _legitext_loi(num)
    return ("https://www.legifrance.gouv.fr/loda/id/%s" % tid) if tid else None


def _lien_texte(cid):
    if not cid:
        return None
    if cid.startswith("JORFTEXT"):
        return "https://www.legifrance.gouv.fr/jorf/id/%s" % cid
    if cid.startswith("LEGITEXT"):
        return "https://www.legifrance.gouv.fr/loda/id/%s" % cid
    return "https://www.legifrance.gouv.fr/jorf/id/%s" % cid


def historique_article(code, article, date=None):
    """HISTORIQUE des versions d'un article de code OU DE LOI : chaque version (dates, état) et le
    TEXTE qui l'a créée ou modifiée (intitulé, nature, date, lien Légifrance vérifié). Source :
    PISTE /consult/getArticle (champs articleVersions + lienModifications). Un texte désigné par
    son numéro (« loi n° 78-17 ») passe par le fonds LODA, comme `resoudre_loi`.
    Seul l'article demandé est retenu : si la cascade en rend un autre, la réponse porte `trouve`
    False, `exact` False, et le `num` et le `lien` de l'article le plus proche.
    Si PISTE n'a pas répondu, la réponse porte `panne` (le message de l'incident) ; une version
    dont le texte modificateur n'a pu être lu garde `modif` à None."""
    d = date or datetime.date.today().strftime("%Y-%m-%d")
    if _RE_NUM_LOI.search(code or ""):
        r = resoudre_loi(code, article, d, exact=True)
    else:
        r = resoudre(code, article, d, exact=True)
    if not r.get("trouve") or not r.get("id"):
        refus = {"trouve": False}
        if r.get("exact") is False:
            refus.update(exact=False, num=r.get("num"), lien=r.get("lien"))
        if r.get("panne"):
            refus["panne"] = r["panne"]
        return refus
    est_loi = "loda" in (r.get("lien") or "")
    try:
        art = (_post("/consult/getArticle", {"id": r["id"]}) or {}).get("article") or {}
    except Exception as e:
        return {"trouve": False, "panne": _panne(e)}
    versions = art.get("articleVersions") or []
    out = []
    panne = None
    for v in versions:
        vid = v.get("id")
        modif = None
        try:
            va = (_post("/consult/getArticle", {"id": vid}) or {}).get("article") or {}
            lm = va.get("lienModifications") or []
            cible = [x for x in lm if x.get("linkOrientation") == "cible" and x.get("linkType") in ("CREE", "MODIFIE")]
            s = cible[0] if cible else (lm[0] if lm else None)
            if s:
                modif = {"titre": re.sub(r"\s+", " ", (s.get("textTitle") or "")).strip(),
                         "nature": s.get("natureText"), "sens": s.get("linkType"),
                         "date": s.get("datePubliTexte") or s.get("dateSignaTexte"),
                         "lien": _lien_texte(s.get("textCid"))}
        except Exception as e:
            panne = _panne(e)
        out.append({"version": v.get("version"), "debut": _iso(v.get("dateDebut")),
                    "fin": _iso_fin(v.get("dateFin")), "etat": v.get("etat"),
                    "lien_version": ("https://www.legifrance.gouv.fr/%s/article_lc/%s"
                                     % ("loda" if est_loi else "codes", vid)) if vid else None,
                    "modif": modif})
    out.sort(key=lambda x: x.get("debut") or "")
    reponse = {"trouve": True, "code": r.get("code") or code, "article": r.get("num") or article,
               "cid": art.get("cid"), "lien": r.get("lien"),
               "texte_actuel": re.sub(r"<[^>]+>", " ", (art.get("texte") or ""))[:900].strip(),
               "versions": out}
    if panne:
        reponse["panne"] = panne
    return reponse


# ==================================================================================================
# CACHE DISQUE DES RÉSOLUTIONS.
#
# Une résolution est une question DATÉE : « où est l'article L. 511-7 du code de la consommation
# au 05/09/2026 ? » a une réponse définitive. La rejouer à chaque « Mettre à jour le tableau »
# refait les mêmes requêtes Légifrance — c'est le premier poste du temps d'attente (mesuré le
# 05/09/2026 sur le dossier 400011). On enveloppe donc les trois résolveurs : réponse trouvée en
# cache → rendue sans réseau ; sinon appel réel, et seules les RÉUSSITES sont mémorisées (une
# panne n'est pas un résultat vide — leçon du 31/08/2026). Le cache vit dans data/cache_disque.db
# et se vide avec `cache_disque.purger("lf_...")` si Légifrance venait à changer ses liens.
#
# Le module de cache est FACULTATIF : sans lui, les résolveurs appellent l'API à chaque fois,
# ce qui est correct, seulement plus lent. Un cache minimal doit exposer trois fonctions :
#   cle(nom, args, kwargs_tries, date) -> str ; lire(cle) -> objet ou None ; ecrire(cle, objet).
# ==================================================================================================
try:
    import cache_disque as _CD
except Exception:
    _CD = None


def _avec_cache_disque(nom_f, f, i_date):
    def _w(*args, **kw):
        d = kw.get("date") if "date" in kw else (args[i_date] if len(args) > i_date else None)
        d = d or datetime.datetime.now().strftime("%Y-%m-%d")
        aa = [a for j, a in enumerate(args) if j != i_date]
        k = _CD.cle(nom_f, aa, sorted((x, y) for x, y in kw.items() if x != "date"), d)
        v = _CD.lire(k)
        if v is not None:
            return v
        r = f(*args, **kw)
        if isinstance(r, dict) and r.get("trouve") and not r.get("panne"):
            _CD.ecrire(k, r)
        return r
    _w.__name__ = f.__name__
    _w.__doc__ = f.__doc__
    return _w


if _CD is not None:
    resoudre = _avec_cache_disque("lf_resoudre", resoudre, 2)
    resoudre_loi = _avec_cache_disque("lf_resoudre_loi", resoudre_loi, 2)
    resoudre_subdivision = _avec_cache_disque("lf_resoudre_subdivision", resoudre_subdivision, 3)


# Démonstration, exécutée seulement au lancement direct (`python legifrance.py [code] [article] [date]`).
# À GARDER EN FIN DE FICHIER : Python exécute le fichier de haut en bas, et une fonction définie plus
# bas n'existerait pas encore au moment de la démonstration (vérifié par test_legifrance.py).
if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "Code de l'environnement"
    article = sys.argv[2] if len(sys.argv) > 2 else "R. 122-5"
    date = sys.argv[3] if len(sys.argv) > 3 else "2016-07-08"
    try:
        r = resoudre(code, article, date)
    except Exception as e:
        print("ERREUR:", e); sys.exit(1)
    if not r["trouve"]:
        print("Article non trouvé. Réponse brute (début):", json.dumps(r["brut"], ensure_ascii=False)[:600]); sys.exit(0)
    print(f"{r['num']} — {code}")
    print(f"Version en vigueur : {r['version_debut']} → {r['version_fin'] or '(en cours)'} (demandé au {date})")
    print(f"Lien : {r['lien']}")
    print("Texte (400 c.) :", r["texte"][:400].replace("\n", " "))
