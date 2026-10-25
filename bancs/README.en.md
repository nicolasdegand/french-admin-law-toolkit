# Benchmarks

Three benchmarks (*bancs d'essai*), and a common measurement harness. All in the
standard library, without dependency, without model; without network, except
the EUR-Lex benchmark, which queries the public endpoint of the Publications
Office.

| folder | what it measures |
|---|---|
| [`fichage/`](fichage/) | does a legal search retrieve the decision that laid down the rule? |
| [`legistique/`](legistique/) | is an instruction amending a text read and applied correctly? |
| [`eurlex/`](eurlex/) | does a search in EUR-Lex retrieve the Union act at stake? |

[`mesurer.py`](mesurer.py) is the measurement harness for the search benchmarks
(nDCG@10, recall, MRR, rank of the first expected result, results by corpus). It
calls your engine through an adapter: see
[`adaptateur_recherche_gabarit.py`](adaptateur_recherche_gabarit.py).

The legislative drafting (*légistique*) benchmark has its own runner,
[`legistique/executer.py`](legistique/executer.py), because it measures not a
ranking but an analysis.

## The common principle

The benchmarks are built on the same conviction: **a useful benchmark is a
benchmark that made something fail.** No case is there to make up the numbers.
The legislative drafting benchmark is a collection of observed errors, each with
its source. The abstracting (*fichage*) benchmark exploits an annotation that
already existed, rather than manufacturing a new one. The EUR-Lex benchmark
showed that the search by question retrieved none of the expected acts.

And the corollary: **the figures serve to compare two configurations on the same
benchmark, never to measure an absolute quality.** The relevance judgments are
incomplete by construction, and the cases are not a representative sample. A
score only has meaning relative to another score obtained under the same
conditions.
