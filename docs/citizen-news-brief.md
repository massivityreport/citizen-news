# Citizen News — brief produit

> **Remplacé par le [brief V2](citizen-news-brief-v2.md)** (une personnelle de 10 sujets, une collective à 17 h). Ce document décrit la V1 (vote, Successive Halving), conservée pour mémoire : ces mécanismes ont été supprimés.

## La promesse

**Citizen News, ce n’est pas Google News. C’est la une choisie par les citoyens.**

La plateforme agrège ce dont parlent les médias, regroupe les articles en sujets, puis permet aux citoyens de décider collectivement quels sujets méritent réellement l’attention publique.

La question centrale n’est pas :

> Quel article aimez-vous ?

Mais :

> De quoi devrions-nous parler aujourd’hui ?

## 1. La home : la une des citoyens

La page d’accueil présente directement **la une citoyenne**. Elle est accessible à tous, sans compte.

Chaque sujet apparaît sous forme de carte comportant :

- un titre factuel ;
- un résumé court ;
- plusieurs sources médiatiques ;
- la date et les évolutions récentes ;
- son niveau de soutien citoyen ;
- la raison explicite de sa présence dans la une.

Par exemple :

- **Priorité commune** — soutenu par des citoyens aux sensibilités différentes ;
- **Forte mobilisation** — beaucoup de citoyens demandent qu’on en parle ;
- **Alerte minoritaire** — très important pour un groupe, encore peu visible ailleurs ;
- **Sous les radars** — peu couvert par les médias, mais jugé important ;
- **Sujet émergent** — progression rapide dans les votes.

Le classement dépend donc d’un score collectif, mais la plateforme ne prétend pas qu’une formule unique définit l’intérêt général. Plusieurs chemins permettent à un sujet d’accéder à la une.

## 2. « À vous de jouer » : l’espace de vote

Après avoir parcouru la une, l’utilisateur arrive à la section :

> **À vous de jouer**  
> Quels sujets devraient recevoir davantage d’attention ?

Citizen News lui présente une succession de sujets à évaluer :

- **Il faut davantage en parler**
- **Ce n’est pas prioritaire**
- **Je ne sais pas / je n’ai pas assez d’informations**

Des comparaisons ponctuelles peuvent également être proposées :

> Lequel de ces deux sujets devrait recevoir davantage d’attention aujourd’hui ?

Le vote n’est pas limité par un budget global : un citoyen peut évaluer autant de sujets qu’il le souhaite. En revanche :

- une personne ne peut compter qu’une fois par sujet ;
- elle peut modifier son choix ;
- les résultats sont masqués avant le vote ;
- l’ordre des sujets comporte une part d’aléatoire ;
- les comportements coordonnés ou artificiels sont détectés.

Un compte léger paraît nécessaire pour que le vote influence réellement le classement. On peut néanmoins permettre de commencer à voter avant l’inscription, puis demander la création du compte pour enregistrer les choix.

## 3. L’émergence par Successive Halving

Les sujets proposés entrent dans une compétition progressive.

### Première vague

Chaque nouveau sujet reçoit un minimum garanti d’évaluations aléatoires. Cela donne une chance réelle aux sujets inconnus.

### Sélection

Après cette première vague, les sujets les plus prometteurs continuent à être présentés. Les autres passent en réserve.

### Accélération

À chaque vague, Citizen News concentre une part croissante des votes sur les sujets qui semblent pouvoir émerger.

Le parcours est le suivant :

1. Tous les nouveaux sujets entrent dans un premier lot de votes.
2. Les candidats prometteurs accèdent au lot suivant.
3. Les autres passent en réserve.
4. Les sujets confirmés deviennent émergents.
5. Quelques sujets en réserve sont périodiquement repêchés.

La **sévérité du halving** est paramétrable :

- nombre minimal de votes avant la première décision ;
- proportion de sujets conservés à chaque vague ;
- nombre de vagues ;
- part du trafic réservée aux nouveaux sujets ;
- part réservée au repêchage.

Cela permet à Citizen News de sélectionner rapidement sans condamner définitivement les sujets éliminés trop tôt.

Le flux de vote mélange volontairement :

- des sujets nouveaux ;
- des sujets ayant déjà un peu de traction ;
- des sujets proches de l’émergence ;
- quelques sujets de réserve à réévaluer.

Ainsi, voter reste intéressant sans transformer le système en concours de popularité.

## 4. « Proposer un sujet » : l’espace des éclaireurs

Les citoyens les plus motivés peuvent créer un compte et accéder aux outils d’exploration.

Ils disposent de plusieurs entrées.

### Ce dont parlent les médias

Une vue générale de l’actualité agrégée à partir des médias :

- sujets les plus couverts ;
- dernières informations ;
- sujets qui progressent rapidement ;
- diversité des sources ;
- comparaison entre la une médiatique et la une citoyenne.

### Explorer par thématique

Navigation par grandes catégories :

- politique ;
- international ;
- société ;
- environnement ;
- économie ;
- sciences et technologies ;
- santé ;
- culture ;
- territoires.

### Rechercher

Un moteur permet de retrouver :

- un événement ;
- une personnalité ;
- un lieu ;
- une institution ;
- une thématique ;
- un article ou un ensemble d’articles.

### Proposer

Lorsqu’un citoyen trouve un sujet insuffisamment visible, il peut demander :

> **Proposer ce sujet aux citoyens**

Le système vérifie d’abord si le sujet existe déjà. S’il existe, l’utilisateur le soutient ou demande sa remise en circulation. Sinon, une nouvelle fiche est créée à partir des articles correspondants.

## 5. Un budget d’une proposition par jour

Chaque compte peut introduire **un seul nouveau sujet par jour**.

Ce budget remplit plusieurs fonctions :

- pousser les éclaireurs à choisir leur priorité ;
- limiter le spam et les campagnes industrielles ;
- éviter que les contributeurs les plus actifs saturent le vote ;
- donner une valeur particulière à l’acte de proposition.

La proposition n’équivaut pas à un vote massif. Elle signifie simplement :

> Je pense que ce sujet mérite d’être testé auprès des citoyens.

Les propositions non utilisées ne devraient pas être cumulables : sinon un compte ancien pourrait lancer trente sujets le même jour.

## 6. Deux formes de participation, sans rôles rigides

Citizen News ne demande pas aux personnes de choisir une identité permanente. Les deux comportements coexistent librement.

| Participation | Action |
|---|---|
| **Consulter et voter** | Lire la une et évaluer les sujets proposés |
| **Explorer et proposer** | Chercher dans l’actualité et introduire un sujet sous-couvert |

Une personne peut simplement consulter pendant plusieurs semaines, puis devenir ponctuellement éclaireuse lorsqu’elle découvre une information importante.

## 7. L’architecture générale

La navigation principale pourrait être très simple :

- **La une citoyenne**
- **À vous de jouer**
- **Explorer**
- **Proposer un sujet**
- **Comment ça marche**

Sur mobile, « À vous de jouer » pourrait aussi rester accessible via un bouton fixe. Il ne faudrait pas que seuls les visiteurs arrivant jusqu’au bas de la une découvrent le vote.

## 8. La transparence comme élément du produit

Chaque sujet devrait permettre d’ouvrir une fiche expliquant :

- pourquoi les articles ont été regroupés ;
- combien de sources le couvrent ;
- combien de citoyens l’ont évalué ;
- comment il a traversé les vagues de sélection ;
- pourquoi il apparaît actuellement dans le feed ;
- si une mobilisation coordonnée a été détectée ;
- les différences de soutien entre groupes, sans leur attribuer d’étiquettes politiques simplistes.

Une page publique expliquerait les paramètres actifs de l’algorithme de Successive Halving.

## Formulation synthétique

> **Citizen News est une plateforme d’actualité participative qui transforme la couverture des médias en une une choisie par les citoyens.**
>
> Tout le monde peut consulter la une et voter sur les sujets qui méritent davantage d’attention. Les citoyens les plus engagés peuvent explorer l’ensemble de l’actualité et proposer, une fois par jour, un sujet encore absent.
>
> Les nouveaux sujets sont testés auprès de la communauté puis sélectionnés progressivement grâce à un mécanisme de Successive Halving. Plusieurs voies permettent d’accéder à la une : soutien général, accord transversal, mobilisation forte, alerte minoritaire ou sous-couverture médiatique.
>
> **Citizen News ne demande pas aux citoyens ce qu’ils aiment. Il leur demande de quoi nous devrions parler.**
