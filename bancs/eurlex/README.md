# Banc EUR-Lex

Deux jeux de 12 questions pour comparer les deux recherches de
[`connecteurs/eurlex.py`](../../connecteurs/eurlex.py) : retrouvent-elles l'acte
de l'Union que la question met en cause ?

```
cd bancs
EURLEX_FONCTION=chercher        python3 mesurer.py --banc eurlex/banc_eurlex.jsonl --adaptateur eurlex/adaptateur_eurlex.py --sortie chercher.json
EURLEX_FONCTION=chercher_termes python3 mesurer.py --banc eurlex/banc_eurlex.jsonl --adaptateur eurlex/adaptateur_eurlex.py --sortie termes.json
python3 mesurer.py --comparer chercher.json termes.json
```

Contrairement aux autres bancs, celui-ci interroge le réseau : le point d'accès
SPARQL public de l'Office des publications, sans compte.

## Les cas

Chaque ligne de [`banc_eurlex.jsonl`](banc_eurlex.jsonl) porte :

| champ | rôle |
|---|---|
| `question` | la question, rédigée comme dans un dossier ; c'est ce que reçoit `chercher` |
| `attendus` | l'acte attendu, par son numéro CELEX ; intitulé vérifié dans Cellar le 25/10/2026 |
| `termes` | les termes que reçoit `chercher_termes` |

Les termes ont été choisis à partir de la seule question, avant tout essai et
sans relire l'intitulé des actes, comme le ferait un utilisateur. Ils n'ont pas
été retouchés après la mesure, même quand ils manquent l'acte : c'est ce que le
banc doit montrer.

Les questions portent sur le droit de l'environnement (évaluation
environnementale, émissions industrielles, accidents majeurs, Natura 2000,
oiseaux, information environnementale, déchets), la TVA, le retour des
étrangers en séjour irrégulier, les marchés publics et le temps de travail.

## Mesure du 25/10/2026

| | `chercher` d'origine | `chercher` refondue | `chercher_termes` |
|---|---:|---:|---:|
| acte trouvé dans les 10 premiers | 0 sur 12 | 9 sur 12 | 9 sur 12 |
| nDCG@10 | 0,000 | 0,564 | 0,496 |
| MRR | 0,000 | 0,507 | 0,415 |
| rang médian de l'acte trouvé | — | 1 | 2 |
| durée des 12 questions | 8,7 s | 36 s | 10 s |

La durée comprend l'état des actes (en vigueur, version consolidée,
rectificatifs) et, pour `chercher`, la recherche dans la jurisprudence, rendue
après les actes.

Les trois actes manqués par `chercher_termes` le sont à cause des termes :
« déduction » ne figure pas dans l'intitulé de la directive TVA, « faune et
flore » n'est pas l'expression de la directive Habitats (« de la faune et de la
flore »), et « déchets » seul est trop général pour faire remonter la
directive-cadre.

`chercher` d'origine ne trouvait aucun acte : les mots extraits de la question
(« environnementale », « étude », « impact »…) ne sont pas ceux des intitulés, et
le point d'accès lui rendait les premiers titres qui contenaient l'un d'eux, avant
tout classement. `chercher` refondue demande à l'index plein texte les titres qui
contiennent au moins deux mots de la question, au singulier ou au pluriel, et les
classe elle-même (voir la docstring de `_classer`). Elle a été réglée sur ce banc :
d'où le banc de contrôle.

## Banc de contrôle

[`banc_eurlex_controle.jsonl`](banc_eurlex_controle.jsonl) : 12 autres questions
(aides d'État, concessions, concurrence, clauses abusives, passagers aériens,
médicaments, PAC, sécurité sociale, détachement, qualifications
professionnelles, eau, services), écrites et validées avant toute modification de
`chercher`, et consultées seulement pour vérifier les réglages. Même format ; on
le désigne par `EURLEX_BANC`.

| | `chercher` d'origine | `chercher` refondue | `chercher_termes` |
|---|---:|---:|---:|
| acte trouvé dans les 10 premiers | 0 sur 12 | 5 sur 12 | 9 sur 12 |
| nDCG@10 | 0,000 | 0,281 | 0,608 |
| MRR | 0,000 | 0,239 | 0,566 |

Le gain de `chercher` se confirme, en plus modeste. Ses échecs tiennent surtout
au vocabulaire : une question rédigée en termes de droit français (« SDAGE »,
« salarié détaché », « diplôme d'architecte ») ne rencontre pas celui des
intitulés de l'Union. `chercher_termes`, qui part des mots de l'intitulé, garde
9 sur 12.

Ce que la mise au point a écarté, mesures à l'appui : les jokers (« proje* »),
trop lents (9 délais dépassés sur 12) ; le classement propre de l'index, qui
favorise les titres commençant par « Projet de… » ; la jurisprudence mélangée aux
actes (3 sur 12 au lieu de 8 sur le premier banc). Faire passer les actes en
vigueur devant les actes abrogés a porté le premier banc de 8 à 9 sur 12 ; sans
effet notable sur le banc de contrôle.

Douze questions ne font pas un échantillon représentatif : comme pour les autres
bancs, les chiffres servent à comparer deux configurations, non à mesurer une
qualité absolue.
