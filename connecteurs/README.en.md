# Connectors to the public sources of law

Five Python modules, standard library only, for querying the official sources
from a program. No dependency, no framework: one file, functions, dictionaries
returned.

| module | source | authentication |
|---|---|---|
| `legifrance.py` | Légifrance, through the PISTE API of the DILA | PISTE account |
| `judilibre.py` | Judilibre, case law of the ordinary courts, through PISTE | PISTE account |
| `travaux.py` | parliamentary proceedings, through Légifrance | PISTE account |
| `eurlex.py` | EUR-Lex, Cellar SPARQL endpoint | none |
| `constit_tables.py` | Constitutional Council (*Conseil constitutionnel*), pending QPC | none |

`eurlex.py` and `constit_tables.py` work immediately, without an account.

## PISTE credentials

Create an account on [piste.gouv.fr](https://piste.gouv.fr/), create an
application, and **subscribe it to each API** you want to use (Légifrance,
Judilibre). A missing subscription shows up as a 403, not as an explicit
message.

The credentials are read, in this order:

1. the environment variables `PISTE_CLIENT_ID` and `PISTE_CLIENT_SECRET`;
2. a JSON file `{"client_id": "...", "client_secret": "..."}` designated by
   `PISTE_CREDENTIALS`, failing that `~/.piste.json`.

They are sent only to `oauth.piste.gouv.fr`, to obtain a token. The token is
kept in memory until it expires, never written to disk. Do not commit your
credentials file.

## Légifrance

```python
import legifrance

legifrance.resoudre("code de la consommation", "L. 511-7", "2024-03-15")
legifrance.resoudre_loi("loi n° 78-17", "6", "2024-03-15")
legifrance.historique_article("code général des collectivités territoriales", "L. 2121-29")
legifrance.chercher_termes("obligation de motivation refus protection fonctionnelle", k=5)
legifrance.etat_connecteur()          # diagnostic : identifiants, jeton, abonnement
```

Three things are worth noting, because they cost time to anyone who discovers
them alone.

**The date is not an ornament.** `resoudre(code, article, date)` returns the
version **in force on that date**, not the current version. In an action for
annulment for excess of power (*recours pour excès de pouvoir*), the relevant
date is that of the contested act, and the current version is almost always the
wrong answer.

**Codes and statutes are two distinct corpora.** An article of an uncodified
statute lives in the LODA corpus, an article of a code in the CODE_DATE corpus.
Looking for "article 6 of Act no. 78-17" in the codes never returns anything,
silently. The module routes by itself when it recognises the number of an Act,
an ordinance or a decree, but the distinction remains something to know.

**An outage is not an empty result.** The responses carry `trouve` (found) and,
in the event of a network or API incident, `panne` (outage). Treating an outage
as an absence leads to concluding that an article does not exist when the
service was unavailable. The module distinguishes the two: your code must do so
too.

A disk cache is **optional**: if a module `cache_disque` exposing
`cle(nom, args, kwargs, date)`, `lire(cle)` and `ecrire(cle, valeur)` can be
imported, the three resolvers are wrapped and dated resolutions, which have a
definitive answer, are not replayed. Only successes are memorised, never
outages. Without this module, everything works, only more slowly.

## Judilibre

```python
import judilibre
judilibre.chercher("responsabilité du fait des produits défectueux", k=5)
judilibre.sante()                     # l'abonnement Judilibre est-il actif ?
```

Natural-language search in the case law of the ordinary courts, with a
publication level (P, B, R, L) analogous to the hierarchy of the Recueil Lebon.
Reuses the authentication of `legifrance.py`.

## Parliamentary proceedings

```python
import travaux
travaux.travaux_pour_article("code de l'environnement", "L. 121-8", "2024-03-15")
```

The principle deserves explanation, because it is not obvious: the version of
the article applicable on the date of the dispute is resolved, the text that
**created** that version is identified (Légifrance `CREE` link), then its
legislative file and its preparatory works are retrieved. A regulatory
provision (R. or D.) has no parliamentary proceedings: the module says so rather
than searching in vain.

## EUR-Lex

```python
import eurlex
eurlex.chercher("protection des données à caractère personnel", k=6)
eurlex.chercher("aides d'État", k=6, secteurs=("3",))     # législation seulement
```

Queries the public Cellar SPARQL endpoint, by keywords in the French titles,
restricted by default to legislation (CELEX sector 3) and to the case law of the
Union (sector 6). No authentication. Returns reference, type, date and EUR-Lex
link.

## Constitutional Council: pending QPC

```python
import constit_tables
constit_tables.maj_qpc_instance()                                  # rafraîchit le tableau
constit_tables.qpc_pendante_sur("code de la sécurité intérieure", "L. 226-1")
```

Retrieves the table of pending cases and answers a precise question: is a
priority question of constitutionality (*question prioritaire de
constitutionnalité*, QPC) pending on this provision? The table changes
constantly and must be refreshed. The file is written in the module's folder, or
in the one designated by `CONSTIT_DOSSIER`.

## Tests and demonstrations

The `test_*.py` files check the modules without network access or PISTE
credentials: the responses of the services queried are simulated. From the
repository root:

```
python -m unittest discover -s connecteurs -v
```

Run directly (`python legifrance.py`, for example), a module executes the
demonstration placed under `if __name__ == "__main__":`, which queries the
sources for real. **This block must stay at the end of the file.** Python runs a
file from top to bottom: a function defined after the demonstration does not
exist yet when it runs, and direct execution fails even though importing the
module works. The test files check this for the modules they cover.

## What is not here

There is no connector to the search interface of the Council of State (*Conseil
d'État*) website. Querying an interface that is not documented as a public API
is not a technical choice but an institutional one, and it is not for this
repository to make it on behalf of others.

## Limits

These modules were written for real use, not to be exhaustive. They cover what a
legal research task needs every day and stop there. APIs evolve: if a response
changes shape, it is the connector that must be corrected, and reporting it here
helps everyone.
