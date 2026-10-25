# -*- coding: utf-8 -*-
"""Adaptateur de mesurer.py pour connecteurs/eurlex.py.

    cd bancs
    EURLEX_FONCTION=chercher        python3 mesurer.py --banc eurlex/banc_eurlex.jsonl \\
        --adaptateur eurlex/adaptateur_eurlex.py --sortie chercher.json
    EURLEX_FONCTION=chercher_termes python3 mesurer.py --banc eurlex/banc_eurlex.jsonl \\
        --adaptateur eurlex/adaptateur_eurlex.py --sortie termes.json
    python3 mesurer.py --comparer chercher.json termes.json

`chercher` reçoit la question ; `chercher_termes`, les termes que le banc associe à cette
question (champ `termes`). Le banc est lu dans EURLEX_BANC (par défaut, banc_eurlex.jsonl ; le
banc de contrôle est banc_eurlex_controle.jsonl)."""
import json
import os
import sys

_ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ICI, "..", "..", "connecteurs"))
import eurlex  # noqa: E402


def _termes():
    chemin = os.environ.get("EURLEX_BANC", os.path.join(_ICI, "banc_eurlex.jsonl"))
    termes = {}
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne and not ligne.startswith("//"):
                q = json.loads(ligne)
                termes[q["question"]] = q.get("termes", [])
    return termes


_TERMES = _termes()


def chercher(question, k=10, fonds=None):
    fonction = os.environ.get("EURLEX_FONCTION", "chercher")
    if fonction == "chercher_termes":
        return eurlex.chercher_termes(_TERMES[question], k=k)
    return eurlex.chercher(question, k=k)
