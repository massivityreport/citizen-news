# API Citizen News

Backend FastAPI + PostgreSQL. Contrat HTTP : [`docs/api-contract.md`](../docs/api-contract.md). Lancement, variables d'environnement et tests : [README racine](../README.md).

## Alimentation en sujets

```
flux RSS ──ingest──▶ articles ──cluster──▶ topics ──▶ GET /api/topics/front, GET /api/vote/next
```

### Commandes

Dans le conteneur (le service `worker` du compose les lance en boucle) :

```bash
docker compose run --rm api python -m app.cli ingest    # récupère les flux de config/feeds.yaml
docker compose run --rm api python -m app.cli cluster   # regroupe les articles en sujets
docker compose run --rm api python -m app.cli refresh   # ingest puis cluster
docker compose run --rm api python -m app.cli run --interval-minutes 15   # refresh en boucle
```

Le service `worker` exécute `run`. Intervalle : variable `INGEST_INTERVAL_MINUTES` (défaut 15). Un flux en erreur (réseau, 404, XML invalide) est consigné dans les logs et n'arrête pas les autres ; `ingest` ne retourne un code d'erreur que si **aucun** flux n'a pu être lu. Toutes les commandes sont idempotentes : les relancer ne duplique rien.

### `config/feeds.yaml`

Une entrée par média : `name` et `feed_url`. Chargement validé (`config/feeds.py`) : URL `http(s)` valide, doublons de nom ou d'URL refusés, champs inconnus refusés. La table `media_sources` est synchronisée à chaque `ingest` (clé : `feed_url` ; un média renommé est mis à jour, un média retiré de la config est conservé avec ses articles).

La liste de départ compte 12 médias ; les URL ont été vérifiées le 26/11/2026. Les Echos (403/503 pour un client automatique) n'est pas inclus. Les articles sont dédupliqués par URL ; le résumé est nettoyé du HTML.

### `config/clustering.yaml`

| Paramètre | Défaut | Effet |
|---|---|---|
| `similarity_threshold` | 0.35 | Similarité cosinus minimale (entre 0 et 1, exclus) pour rattacher un article à un sujet existant. |
| `window_hours` | 48 | Fenêtre de temps : seuls les articles publiés dans la fenêtre sont regroupés, et un sujet sans nouvel article depuis plus longtemps n'accepte plus de rattachement. La une et `vote/next` ne montrent que les sujets actifs dans cette fenêtre. |
| `min_sources_for_front` | 2 | Nombre de **médias distincts** minimal pour qu'un sujet soit visible. Plusieurs articles d'un même média comptent pour une seule source. |

#### Comment ça marche

Chaque article devient un vecteur TF-IDF : le titre compte 3 fois (il est répété avant le résumé), les accents et la casse sont normalisés (« Élysée » = « elysee »), les mots vides français sont ignorés. Les articles non rattachés sont traités du plus ancien au plus récent : chacun rejoint le sujet dont le centroïde est le plus proche si la similarité atteint le seuil, sinon il crée un sujet (`state=new`, `wave=0`). Un article déjà rattaché n'est jamais déplacé, d'où l'idempotence.

Le titre du sujet est celui de l'article le plus représentatif (le plus proche du centroïde ; à 0,01 près, le plus court) et le résumé est celui du même article, tronqué à ~280 caractères. `first_seen_at` et `updated_at` sont la date du plus ancien et du plus récent article du sujet.

#### Choisir le seuil

- Trop **bas** : des sujets distincts fusionnent (le même ministre dans deux affaires différentes).
- Trop **haut** : un même événement reste éclaté en plusieurs sujets à une seule source, donc invisible.
- Méthode : lancer `refresh` sur une base vide, parcourir `GET /api/topics/front?limit=50` et repérer, d'une part, les sujets qui mélangent des articles sans rapport (monter le seuil), d'autre part les doublons évidents entre sujets (baisser le seuil). Sur les vrais flux (~350 articles), 0,35 regroupe correctement les articles d'un même événement (10 médias sur une même affaire judiciaire) sans fusion abusive observée.
- Le TF-IDF est réajusté à chaque exécution sur les articles de la fenêtre (les poids IDF varient donc d'un run à l'autre) ; le résultat reste déterministe pour un état de base et une date donnés. Un article déjà rattaché n'est jamais réévalué : **changer le seuil ne recalcule pas l'existant** et ne vaut que pour les nouveaux articles.
- Après changement, repartir d'une base vide (`docker compose down -v`) : les rattachements existants ne sont pas recalculés.

### Endpoints

- `GET /api/topics/front?limit=20` : sujets ayant au moins `min_sources_for_front` médias distincts, du plus récemment mis à jour au plus ancien. Réponse mise en cache 5 secondes ; 2 requêtes SQL (sujets, puis articles de ces sujets). `sources` contient une entrée par média (son article le plus récent). **Provisoire** : `support` vaut `{"level": "low", "votes_count": 0}` et `reason` vaut `emerging` ; ce calcul est isolé dans `app/services/support.py` (`support_for`), que la tâche votes/halving remplacera.
- `GET /api/vote/next?count=10&seen=1,2` : sujets éligibles en ordre aléatoire, hors `seen`, sans `support` ni `reason`. **Provisoire** : le halving remplacera le tirage aléatoire.

### Code

```
app/cli.py                  ingest / cluster / refresh / run
app/services/ingest.py      récupération (httpx), parsing (feedparser), upsert
app/services/clustering.py  TF-IDF + similarité cosinus
app/services/topics.py      éligibilité des sujets, construction des TopicCard
app/services/support.py     support/raison (provisoire)
app/routers/topics.py       /api/topics/front, /api/vote/next
config/feeds.py, clustering.py   chargeurs validés
tests/fixtures/             flux RSS d'exemple (aucun accès réseau dans les tests)
```
