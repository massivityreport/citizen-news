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

## Comptes et sessions

Flux (détail des routes dans le [contrat](../docs/api-contract.md)) :

```
POST /api/auth/magic-link ─▶ login_tokens (hash) ─▶ e-mail {APP_BASE_URL}/connexion?token=…
POST /api/auth/verify     ─▶ jeton consommé, compte créé au 1er usage ─▶ sessions (hash) + cookie cn_session
GET /api/me · POST /api/auth/logout · POST /api/votes/claim · GET /api/votes/mine   (cookie requis)
```

- **Jetons** : `secrets.token_urlsafe(32)`, stockés uniquement hachés (SHA-256) : lien magique dans `login_tokens` (expire après `LOGIN_TOKEN_TTL_MINUTES`, usage unique consommé par un `UPDATE … WHERE used_at IS NULL` atomique), session dans `sessions` (`SESSION_TTL_DAYS`). Pas de JWT : la déconnexion révoque la session côté serveur. Jetons expirés ou utilisés et sessions expirées sont purgés à chaque vérification (au bout d'un jour pour les jetons).
- **Cookie** `cn_session` : `httpOnly`, `SameSite=Lax`, `Secure` si `COOKIE_SECURE=true`, `Max-Age` = durée de session.
- **Pas d'énumération** : `magic-link` répond `202 {}` dans tous les cas (l'e-mail est envoyé aussi pour une adresse inconnue : le compte n'est créé qu'à la vérification) ; l'échec d'envoi n'est pas visible de l'appelant. `verify` répond `400` au message unique « Lien de connexion invalide ou expiré » (inconnu, expiré ou déjà utilisé).
- **Données personnelles** : `accounts` ne contient que l'e-mail et la date de création. Aucune IP en base ; le limiteur de débit les garde en mémoire, le temps de la fenêtre. L'e-mail dans `login_tokens` est supprimé un jour après expiration ou usage.
- **Protéger une route** : `account: Account = Depends(current_account)` (`app/deps.py`) ; `401 {"detail": "Authentification requise"}` sans session valide.

### E-mail

`app/services/mailer.py` : interface `Mailer.send(to, subject, body)`, deux implémentations choisies par `MAIL_BACKEND`. `smtp` : `smtplib`, `SMTP_HOST` obligatoire (l'application refuse de démarrer sans), STARTTLS par défaut, authentification si `SMTP_USER` est défini. `console` : écrit le message (lien compris) dans le logger `app.mail` : développement seulement. L'envoi se fait après la réponse (`BackgroundTasks`) ; un échec est journalisé sans adresse ni lien.

### Limitation de débit

`app/services/ratelimit.py` : fenêtre glissante en mémoire (interface `RateLimiter`, horloge injectable), **par processus API** (plusieurs processus multiplient la limite ; brancher un stockage partagé derrière l'interface si besoin). Au-delà : `429 {"detail": …}` et en-tête `Retry-After` (secondes).

| Route | Clé | Variable (défaut) |
|---|---|---|
| `POST /api/auth/magic-link` | IP | `RATE_LIMIT_MAGIC_LINK_PER_IP` (20) |
| `POST /api/auth/magic-link` | e-mail normalisé (haché en mémoire) | `RATE_LIMIT_MAGIC_LINK_PER_EMAIL` (5) |
| `POST /api/auth/verify` | IP | `RATE_LIMIT_VERIFY_PER_IP` (30) |
| `POST /api/votes/claim` | compte | `RATE_LIMIT_CLAIM_PER_ACCOUNT` (30) |

Fenêtre : `RATE_LIMIT_WINDOW_SECONDS` (3600). L'IP est celle de la connexion ; avec `TRUST_PROXY=true`, c'est la **dernière** entrée de `X-Forwarded-For` (celle qu'ajoute le proxy de confiance : les entrées précédentes sont falsifiables). N'activez `TRUST_PROXY` que derrière un proxy qui écrase ou complète cet en-tête, sinon n'importe qui contourne la limite.

### Votes anonymes

Les votes faits sans compte restent dans le navigateur : rien n'est stocké côté serveur avant `claim`, donc ils ne comptent pas dans le classement. `POST /api/votes/claim {votes:[{topic_id,choice}]}` : un vote déjà présent sur le sujet n'est jamais écrasé (contrainte `UNIQUE(account_id, topic_id)` + `ON CONFLICT DO NOTHING`), les sujets inconnus sont ignorés, un sujet répété dans le lot compte une fois (le premier gagne), `claimed` est le nombre de votes réellement créés. Un lot de plus de `CLAIM_MAX_VOTES` (200) votes est refusé en `422` (rien n'est enregistré). `POST /api/votes` (vote direct) viendra avec la tâche votes/halving.

Toute erreur de validation (`422`) renvoie `{"detail": "Requête invalide (champ : …)"}` comme le contrat le demande.

### Code

```
app/cli.py                  ingest / cluster / refresh / run
app/services/ingest.py      récupération (httpx), parsing (feedparser), upsert
app/services/clustering.py  TF-IDF + similarité cosinus
app/services/topics.py      éligibilité des sujets, construction des TopicCard
app/services/support.py     support/raison (provisoire)
app/routers/topics.py       /api/topics/front, /api/vote/next
app/routers/auth.py         /api/auth/*, /api/me
app/routers/votes.py        /api/votes/claim, /api/votes/mine
app/services/auth.py        jetons, comptes, sessions
app/services/mailer.py      Mailer (SMTP, console)
app/services/ratelimit.py   limitation de débit
app/deps.py                 current_account, IP cliente
config/feeds.py, clustering.py   chargeurs validés
tests/fixtures/             flux RSS d'exemple (aucun accès réseau dans les tests)
```
