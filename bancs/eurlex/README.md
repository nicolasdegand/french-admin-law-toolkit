# Banc EUR-Lex

12 questions pour comparer les deux recherches de
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

| | `chercher` | `chercher_termes` |
|---|---:|---:|
| acte trouvé dans les 10 premiers | 0 sur 12 | 9 sur 12 |
| nDCG@10 | 0,000 | 0,496 |
| MRR | 0,000 | 0,415 |
| rang médian de l'acte trouvé | — | 2 |
| durée des 12 questions | 8,7 s | 2,2 s |

Les trois actes manqués par `chercher_termes` le sont à cause des termes :
« déduction » ne figure pas dans l'intitulé de la directive TVA, « faune et
flore » n'est pas l'expression de la directive Habitats (« de la faune et de la
flore »), et « déchets » seul est trop général pour faire remonter la
directive-cadre.

`chercher` ne trouve aucun acte : les mots qu'elle extrait de la question
(« environnementale », « étude », « impact »…) ne sont pas ceux des intitulés, et
le point d'accès lui rend les premiers titres qui contiennent l'un d'eux, avant
tout classement.

Douze questions ne font pas un échantillon représentatif : comme pour les autres
bancs, les chiffres servent à comparer deux configurations, non à mesurer une
qualité absolue.
