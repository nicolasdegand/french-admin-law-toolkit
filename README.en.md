# Generic tools for administrative law and legal informatics

French version: [README.md](README.md). Code, benchmark cases and JSON keys are in French, since they operate on French legal texts; the English READMEs explain each of them. The French text prevails.

Benchmarks, connectors to the public sources of law and a method note, taken
from a personal exploratory work on the use of language models in the work of
the administrative judge. What is here is what may be of use to others: nothing
is specific to any particular application.

**Standard library only.** Python 3.8 or later. No dependency to install, no
model, no service to subscribe to, except for the two connectors that query the
PISTE API and require a free account.

## What the repository contains

### [`bancs/`](bancs/): measure, rather than believe

**[`bancs/fichage/`](bancs/fichage/)**: A method for building a benchmark for
legal search **without annotating a single question**. The abstracting
(*fichage*) of case law already pairs a point of law written by a judge with the
decision that laid it down: that is a question and answer pair produced by an
expert, and there are tens of thousands of them in open data. It only needs to be
turned around. The program builds the benchmark, with the three precautions that
make it valid (no leakage, no unfindable question, no classification path taken
for a question).

**[`bancs/legistique/`](bancs/legistique/)**: 89 cases to measure whether a
program, or a model, correctly reads the instructions by which one normative text
amends another, and applies them at the right place in the text in force. Each
case was added because an implementation had got it wrong: "ainsi rédigé" (worded
as follows) taken for a replacement operator when it also serves for insertion, a
table row counted as a paragraph (*alinéa*), a range of articles whose middle
element is forgotten.

**[`bancs/eurlex/`](bancs/eurlex/)**: 12 questions to compare the two EUR-Lex
searches of `connecteurs/eurlex.py`: do they retrieve the Union act at stake?
The only benchmark that uses the network.

**[`bancs/mesurer.py`](bancs/mesurer.py)**: The measurement harness: nDCG@10,
recall, MRR, rank of the first expected result, and the breakdown by corpus. It
calls your engine through an adapter of a few lines and looks for the identifiers
in your results itself, whatever the names of your fields.

### [`connecteurs/`](connecteurs/): reach the official sources

Five modules for querying Légifrance, Judilibre, EUR-Lex, the parliamentary
proceedings and the priority questions of constitutionality (QPC) pending before
the Constitutional Council (*Conseil constitutionnel*). Two of them work without
any account. The README mainly says what costs time to anyone who discovers them
alone: the version date is not an ornament, codes and statutes are two distinct
corpora, and an outage is not an empty result.

### [`distillation/`](distillation/): extract the form, not the substance

A method note: how to draw from judicial open data the **established formulas**
of a type of decision and a **nomenclature of pleas** (*moyens*), by a
statistical and not a generative process, in which nothing can be hallucinated
because no model reads the decisions. With the pitfalls that silently produce
thousands of pleas that do not exist.

## The common thread

These four pieces answer the same question: **how do we know that a legal tool
does what it claims to do?**

The answer adopted holds in three ideas. We measure on cases that made something
fail, not on a flattering sample. We prefer the annotation that already exists to
the one we would manufacture. And we choose, whenever possible, a verifiable
process over a process that asks to be believed: a count can be checked by opening
three documents, which a generation does not allow.

## Disclaimer

This repository is a **personal** work. It does not commit any institution and
reflects the position of none. The decisions, texts and analyses cited are
public; no personal data, no element of a case file, no internal document appears
here.

The tools are provided as they are: they were written for real use, not to be
exhaustive, and they stop where that use stopped.

## Licence

MIT, see [LICENSE](LICENSE). The public data cited (Légifrance, open data of the
justice system, EUR-Lex, Constitutional Council) remain governed by their own
licences, generally the Etalab open licence.

## Contributing

A benchmark case that made your implementation fail is the most useful
contribution. A connector that stops working because an API changed its shape
deserves to be reported: it helps everyone.
