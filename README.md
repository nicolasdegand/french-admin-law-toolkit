# Outils génériques pour le droit administratif et le numérique juridique

English version: [README.en.md](README.en.md)

Des bancs d'essai, des connecteurs vers les sources publiques du droit et une
note de méthode, extraits d'un travail personnel d'exploration sur l'usage des
modèles de langage dans le travail du juge administratif. Ce qui est ici est ce
qui peut servir à d'autres : rien n'est propre à une application particulière.

**Bibliothèque standard uniquement.** Python 3.8 ou plus récent. Aucune
dépendance à installer, aucun modèle, aucun service à souscrire, sauf pour les
deux connecteurs qui interrogent l'API PISTE et demandent un compte gratuit.

## Ce que contient le dépôt

### [`bancs/`](bancs/) — mesurer, plutôt que croire

**[`bancs/fichage/`](bancs/fichage/)** — Une méthode pour construire un banc
d'évaluation de la recherche juridique **sans annoter une seule question**. Le
fichage de la jurisprudence associe déjà un point de droit rédigé par un
magistrat à la décision qui l'a posé : c'est un couple question-réponse produit
par un expert, et il y en a des dizaines de milliers dans l'open data. Il suffit
de le retourner. Le programme construit le banc, avec les trois précautions qui
en font la validité (pas de fuite, pas de question introuvable, pas de chemin de
classement pris pour une question).

**[`bancs/legistique/`](bancs/legistique/)** — 89 cas pour mesurer si un
programme, ou un modèle, lit correctement les instructions par lesquelles un
texte normatif en modifie un autre, et les applique au bon endroit du texte en
vigueur. Chaque cas a été ajouté parce qu'une implémentation s'y était trompée :
« ainsi rédigé » pris pour un opérateur de remplacement alors qu'il sert aussi à
l'insertion, une ligne de tableau comptée pour un alinéa, une plage d'articles
dont l'élément intermédiaire est oublié.

**[`bancs/eurlex/`](bancs/eurlex/)** — 12 questions pour comparer les deux
recherches d'EUR-Lex de `connecteurs/eurlex.py` : retrouvent-elles l'acte de
l'Union en cause ? Le seul banc qui interroge le réseau.

**[`bancs/mesurer.py`](bancs/mesurer.py)** — Le harnais de mesure : nDCG@10,
rappel, MRR, rang du premier attendu, et le détail par fonds. Il appelle votre
moteur à travers un adaptateur de quelques lignes et cherche lui-même les
identifiants dans vos résultats, quel que soit le nom de vos champs.

### [`connecteurs/`](connecteurs/) — atteindre les sources officielles

Cinq modules pour interroger Légifrance, Judilibre, EUR-Lex, les travaux
parlementaires et les QPC en instance devant le Conseil constitutionnel. Deux
d'entre eux fonctionnent sans aucun compte. Le README dit surtout ce qui coûte du
temps à qui les découvre seul : la date de version n'est pas un ornement, les
codes et les lois sont deux fonds distincts, et une panne n'est pas un résultat
vide.

### [`distillation/`](distillation/) — extraire la forme, pas le fond

Une note de méthode : comment tirer de l'open data judiciaire les **formules
consacrées** d'un type de décision et une **nomenclature des moyens**, par un
procédé statistique et non génératif, où rien ne peut être halluciné parce
qu'aucun modèle ne lit les décisions. Avec les pièges qui font produire, en
silence, des milliers de moyens qui n'existent pas.

## Le fil commun

Ces quatre morceaux répondent à la même question : **comment sait-on qu'un outil
juridique fait ce qu'il prétend faire ?**

La réponse retenue tient en trois idées. On mesure sur des cas qui ont fait
échouer quelque chose, pas sur un échantillon flatteur. On préfère l'annotation
qui existe déjà à celle qu'on fabriquerait. Et l'on choisit, quand c'est
possible, un procédé vérifiable plutôt qu'un procédé qui demande à être cru : un
comptage se contrôle en ouvrant trois documents, ce que ne permet pas une
génération.

## Avertissement

Ce dépôt est un travail **personnel**. Il n'engage aucune institution et ne
reflète la position d'aucune. Les décisions, textes et analyses cités sont
publics ; aucune donnée personnelle, aucun élément de dossier, aucun document
interne ne figure ici.

Les outils sont fournis tels quels : ils ont été écrits pour un usage réel, non
pour être exhaustifs, et ils s'arrêtent là où cet usage s'arrêtait.

## Licence

MIT, voir [LICENSE](LICENSE). Les données publiques citées (Légifrance,
open data de la justice, EUR-Lex, Conseil constitutionnel) restent régies par
leurs licences propres, généralement la licence ouverte Etalab.

## Contribuer

Un cas de banc qui a fait échouer votre implémentation est la contribution la
plus utile. Un connecteur qui cesse de fonctionner parce qu'une API a changé de
forme mérite d'être signalé : cela sert à tout le monde.
