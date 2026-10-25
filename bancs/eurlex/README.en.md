# EUR-Lex benchmark

12 questions to compare the two searches of
[`connecteurs/eurlex.py`](../../connecteurs/eurlex.py): do they retrieve the
Union act at stake in the question?

```
cd bancs
EURLEX_FONCTION=chercher        python3 mesurer.py --banc eurlex/banc_eurlex.jsonl --adaptateur eurlex/adaptateur_eurlex.py --sortie chercher.json
EURLEX_FONCTION=chercher_termes python3 mesurer.py --banc eurlex/banc_eurlex.jsonl --adaptateur eurlex/adaptateur_eurlex.py --sortie termes.json
python3 mesurer.py --comparer chercher.json termes.json
```

Unlike the other benchmarks, this one uses the network: the public SPARQL
endpoint of the Publications Office, without an account.

## The cases

Each line of [`banc_eurlex.jsonl`](banc_eurlex.jsonl) carries:

| field | role |
|---|---|
| `question` | the question, worded as in a case file; this is what `chercher` receives |
| `attendus` | the expected act, by its CELEX number; title checked in Cellar on 25/10/2026 |
| `termes` | the terms that `chercher_termes` receives |

The terms were chosen from the question alone, before any run and without
reading the titles of the acts, as a user would. They were not adjusted after
the measurement, even when they miss the act: that is what the benchmark must
show.

The questions cover environmental law (environmental assessment, industrial
emissions, major accidents, Natura 2000, birds, environmental information,
waste), VAT, the return of irregularly staying foreigners, public procurement
and working time.

## Measurement of 25/10/2026

| | `chercher` | `chercher_termes` |
|---|---:|---:|
| act found in the first 10 | 0 of 12 | 9 of 12 |
| nDCG@10 | 0.000 | 0.496 |
| MRR | 0.000 | 0.415 |
| median rank of the act found | — | 2 |
| duration of the 12 questions | 8.7 s | 2.2 s |

The three acts missed by `chercher_termes` are missed because of the terms:
"déduction" is not in the title of the VAT directive, "faune et flore" is not
the wording of the Habitats directive ("de la faune et de la flore"), and
"déchets" alone is too general to bring up the framework directive.

`chercher` finds no act: the words it extracts from the question
("environnementale", "étude", "impact"…) are not those of the titles, and the
endpoint returns the first titles containing any of them, before any ranking.

Twelve questions are not a representative sample: as for the other benchmarks,
the figures serve to compare two configurations, not to measure an absolute
quality.
