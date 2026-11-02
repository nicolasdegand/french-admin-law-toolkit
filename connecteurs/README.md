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
**produit** cette version (liens de modification de Légifrance), puis on récupère
son dossier législatif et ses travaux préparatoires. Une disposition
réglementaire (R. ou D.) n'a pas de travaux parlementaires : le module le dit
plutôt que de chercher en vain.

Légifrance cite parfois plusieurs textes pour une même version, sans dire lequel
a produit la rédaction en cause. Le module ne les départage pas : il les renvoie
tous dans `textes`, chacun avec ses travaux, avec un `avertissement`.

La première version d'un article dans un code ne cite souvent que le texte qui
l'y a inséré, par exemple l'ordonnance n° 2000-914 pour le code de
l'environnement. Les travaux de ce texte n'apprennent rien sur l'intention du
législateur quand la codification s'est faite à droit constant. Le module remonte
donc à la disposition dont l'article est issu, que Légifrance indique (l'article
L. 512-1 du code de l'environnement vient de l'article 3 de la loi n° 76-663), et
renvoie les textes qui ont produit sa rédaction au jour de la codification. La
réponse le signale par un champ `codification`, qui nomme le texte de
codification et la disposition d'origine.

**Le module renvoie des liens, pas le contenu des pièces.** Il donne l'exposé des
motifs, la note de travaux préparatoires publiée au Journal officiel et la liste
des pièces du dossier législatif (projet, rapports, débats, textes adoptés),
chacune avec son lien. Le texte des rapports et des débats n'est pas récupéré :
pour le citer, il faut ouvrir la pièce. Toutes les pièces sont renvoyées.
Une loi qui ratifie des ordonnances est aussi rattachée à leurs dossiers : le
module retient le dossier de la loi elle-même, et liste les autres dans
`autres_dossiers`. Lorsque le texte créateur est une
ordonnance, ou semble être une codification, la réponse porte un
`avertissement` qui indique où chercher l'intention du législateur.

Une ordonnance n'a pas de débats parlementaires. Pour elle, la réponse porte un
champ `ordonnance` qui donne, quand Légifrance les indique, le rapport au
Président de la République et la loi de ratification, pris dans le dossier de
l'ordonnance, et la loi d'habilitation, cherchée parmi les lois que citent les
visas (« Vu la loi n° …, notamment son article … »). Quand le rapport au
Président désigne la loi d'habilitation, seule celle-ci est renvoyée
(`habilitation`) ; sinon, les lois d'habilitation potentielles le sont toutes,
sans être départagées (`habilitations_potentielles`).

## EUR-Lex

```python
import eurlex
eurlex.chercher("protection des données à caractère personnel", k=6)
eurlex.chercher("aides d'État", k=6, secteurs=("3",))     # législation seulement
eurlex.chercher_termes(["émissions industrielles"], k=6)  # tous les termes, dans le titre
eurlex.resoudre("directive 2011/92/UE")                    # par le numéro : acte, affaire, CELEX
```

Interroge le point d'accès SPARQL public Cellar, par mots-clés dans les titres
français, restreint par défaut à la législation (secteur CELEX 3) et à la
jurisprudence de l'Union (secteur 6). Aucune authentification. Rend référence,
type, titre, date et lien EUR-Lex.

`chercher` part d'une question rédigée librement ; elle reconnaît en outre
quelques actes par leur sigle (RGPD, DSA…) et le numéro d'un acte cité, et renvoie
les actes d'abord, puis la jurisprudence. `chercher_termes` prend les termes que
vous choisissez et ne retient que les titres qui les contiennent tous, par
l'index plein texte du point d'accès : réponse en une seconde environ, titres
classés par pertinence, législation par défaut, rectificatifs rattachés à leur
acte. Un terme est cherché tel quel (« projet » ne trouve pas « projets ») :
reprenez les mots de l'intitulé.

Sur les bancs de [`bancs/eurlex/`](../bancs/eurlex/), `chercher_termes` trouve
l'acte attendu pour 9 questions sur 12, sur le banc de réglage comme sur le banc
de contrôle ; `chercher`, pour 9 sur le banc qui a servi à la régler et 5 sur le
banc de contrôle : une question rédigée en termes de droit français (« SDAGE »,
« étude d'impact ») ne rencontre pas le vocabulaire des actes de l'Union.

Les deux fonctions donnent aussi l'état de chaque acte, en une requête de plus : `en_vigueur`,
`fin_de_validite`, la dernière `version_consolidee` (numéro, date, lien) et la
liste complète des `rectificatifs`. La version consolidée est le texte à lire ;
seul le texte publié au Journal officiel fait foi. `etat=False` s'en dispense ; `chercher`
garde alors `en_vigueur` pour les actes de législation, tiré du classement, sans requête de plus ;
`eurlex.etat_des_actes([...])` interroge directement des numéros CELEX.

`resoudre` part d'une référence telle qu'on l'écrit (« règlement (CE) n° 1013/2006 »,
« directive 92/43/CEE », « C-461/17 », un numéro CELEX) : elle en déduit le numéro
CELEX et vérifie dans Cellar que l'acte ou l'affaire existe, avec son état. Une
référence qui se trompe de type est signalée (« directive 2016/679 » : c'est un
règlement), comme un acte dont le titre ne reprend pas le numéro cité. C'est la
fonction à utiliser pour vérifier une citation.

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
