# Connecteurs vers les sources publiques du droit

Cinq modules Python, bibliothèque standard uniquement, pour interroger les
sources officielles depuis un programme. Aucune dépendance, aucun cadre : un
fichier, des fonctions, des dictionnaires en retour.

| module | source | authentification |
|---|---|---|
| `legifrance.py` | Légifrance, via l'API PISTE de la DILA | compte PISTE |
| `judilibre.py` | Judilibre, jurisprudence judiciaire, via PISTE | compte PISTE |
| `travaux.py` | travaux parlementaires, via Légifrance | compte PISTE |
| `eurlex.py` | EUR-Lex, point d'accès SPARQL Cellar | aucune |
| `constit_tables.py` | Conseil constitutionnel, QPC en instance | aucune |

`eurlex.py` et `constit_tables.py` fonctionnent immédiatement, sans compte.

## Identifiants PISTE

Créez un compte sur [piste.gouv.fr](https://piste.gouv.fr/), créez une
application, et **abonnez-la à chaque API** que vous voulez utiliser
(Légifrance, Judilibre). Un abonnement manquant se manifeste par un 403, non par
un message explicite.

Les identifiants sont lus, dans cet ordre :

1. les variables d'environnement `PISTE_CLIENT_ID` et `PISTE_CLIENT_SECRET` ;
2. un fichier JSON `{"client_id": "...", "client_secret": "..."}` désigné par
   `PISTE_CREDENTIALS`, à défaut `~/.piste.json`.

Ils ne sont transmis qu'à `oauth.piste.gouv.fr`, pour obtenir un jeton. Le jeton
est gardé en mémoire jusqu'à son expiration, jamais écrit sur disque. Ne
committez pas votre fichier d'identifiants.

## Légifrance

```python
import legifrance

legifrance.resoudre("code de la consommation", "L. 511-7", "2024-03-15")
legifrance.resoudre_loi("loi n° 78-17", "6", "2024-03-15")
legifrance.historique_article("code général des collectivités territoriales", "L. 2121-29")
legifrance.chercher_termes("obligation de motivation refus protection fonctionnelle", k=5)
legifrance.etat_connecteur()          # diagnostic : identifiants, jeton, abonnement
```

Trois choses valent d'être notées, parce qu'elles coûtent du temps à qui les
découvre seul.

**La date n'est pas un ornement.** `resoudre(code, article, date)` rend la
version **en vigueur à cette date**, non la version actuelle. En excès de
pouvoir, la date pertinente est celle de l'acte attaqué, et la version actuelle
est presque toujours la mauvaise réponse.

**Les codes et les lois sont deux fonds distincts.** Un article de loi non
codifiée vit dans le fonds LODA, un article de code dans le fonds CODE_DATE.
Chercher « l'article 6 de la loi n° 78-17 » dans les codes ne rend jamais rien,
silencieusement. Le module aiguille tout seul quand il reconnaît un numéro de
loi, d'ordonnance ou de décret, mais la distinction reste à connaître.

**Une panne n'est pas un résultat vide.** Les réponses portent `trouve` et,
en cas d'incident réseau ou d'API, `panne`. Traiter une panne comme une absence
conduit à conclure qu'un article n'existe pas alors que le service était
indisponible. Le module distingue les deux : votre code doit le faire aussi.

Un cache disque est **facultatif** : si un module `cache_disque` exposant
`cle(nom, args, kwargs, date)`, `lire(cle)` et `ecrire(cle, valeur)` est
importable, les trois résolveurs sont enveloppés et les résolutions datées, qui
ont une réponse définitive, ne sont pas rejouées. Seules les réussites sont
mémorisées, jamais les pannes. Sans ce module, tout fonctionne, en plus lent.

## Judilibre

```python
import judilibre
judilibre.chercher("responsabilité du fait des produits défectueux", k=5)
judilibre.sante()                     # l'abonnement Judilibre est-il actif ?
```

Recherche en langage naturel dans la jurisprudence judiciaire, avec un niveau de
publication (P, B, R, L) analogue à la hiérarchie du Lebon. Réutilise
l'authentification de `legifrance.py`.

## Travaux parlementaires

```python
import travaux
travaux.travaux_pour_article("code de l'environnement", "L. 121-8", "2024-03-15")
```

Le principe mérite d'être expliqué, parce qu'il n'est pas évident : on résout la
version de l'article applicable à la date du litige, on identifie le texte qui a
**créé** cette version (lien `CREE` de Légifrance), puis on récupère son dossier
législatif et ses travaux préparatoires. Une disposition réglementaire (R. ou
D.) n'a pas de travaux parlementaires : le module le dit plutôt que de chercher
en vain.

**Le module rend des liens, pas le contenu des pièces.** Il donne l'exposé des
motifs, la note de travaux préparatoires publiée au Journal officiel et la liste
des pièces du dossier législatif (projet, rapports, débats, textes adoptés),
chacune avec son lien. Le texte des rapports et des débats n'est pas récupéré :
pour le citer, il faut ouvrir la pièce. Lorsque le texte créateur est une
ordonnance, ou semble être une codification, la réponse porte un
`avertissement` qui indique où chercher l'intention du législateur.

## EUR-Lex

```python
import eurlex
eurlex.chercher("protection des données à caractère personnel", k=6)
eurlex.chercher("aides d'État", k=6, secteurs=("3",))     # législation seulement
```

Interroge le point d'accès SPARQL public Cellar, par mots-clés dans les titres
français, restreint par défaut à la législation (secteur CELEX 3) et à la
jurisprudence de l'Union (secteur 6). Aucune authentification. Rend référence,
type, date et lien EUR-Lex.

## Conseil constitutionnel : les QPC en instance

```python
import constit_tables
constit_tables.maj_qpc_instance()                                  # rafraîchit le tableau
constit_tables.qpc_pendante_sur("code de la sécurité intérieure", "L. 226-1")
```

Récupère le tableau des affaires en instance et répond à une question précise :
une QPC est-elle pendante sur cette disposition ? Le tableau évolue en
permanence, il faut le rafraîchir. Le fichier est écrit dans le dossier du
module, ou dans celui que désigne `CONSTIT_DOSSIER`.

## Tests et démonstrations

Les fichiers `test_*.py` vérifient les modules sans réseau ni identifiants
PISTE : les réponses des services interrogés y sont simulées. Depuis la racine
du dépôt :

```
python -m unittest discover -s connecteurs -v
```

Lancé directement (`python legifrance.py`, par exemple), un module exécute la
démonstration placée sous `if __name__ == "__main__":`, qui interroge réellement
les sources. **Ce bloc doit rester à la fin du fichier.** Python exécute un
fichier de haut en bas : une fonction définie après la démonstration n'existe
pas encore quand celle-ci s'exécute, et le lancement direct échoue alors que
l'import du module fonctionne. Les fichiers de test le vérifient pour les
modules qu'ils couvrent.

## Ce qui n'est pas ici

Il n'y a pas de connecteur vers l'interface de recherche du site du Conseil
d'État. Interroger une interface qui n'est pas documentée comme une API publique
n'est pas un choix technique mais un choix institutionnel, et il n'appartient
pas à ce dépôt de le faire pour autrui.

## Limites

Ces modules ont été écrits pour un usage réel, pas pour être exhaustifs. Ils
couvrent ce dont un travail de recherche juridique a besoin tous les jours et
s'arrêtent là. Les API évoluent : si une réponse change de forme, c'est le
connecteur qu'il faut corriger, et le signaler ici sert à tout le monde.
