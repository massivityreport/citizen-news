# Citizen News — front (`web/`)

React + Vite + TypeScript, React Router, TanStack Query, CSS modules. Interface en français, mobile d'abord.

## Commandes

```sh
npm install
npm run dev      # http://localhost:5173, API simulée par défaut
npm run lint
npm test
npm run build    # sortie statique dans dist/
```

## API réelle ou simulée

| `VITE_USE_MOCKS` | Comportement |
|---|---|
| `true` (défaut en `npm run dev`) | `web/mocks/` intercepte `fetch` sur `/api/*` (état en mémoire, sujets fictifs). Rien n'est inclus dans le build de production. |
| `false` (défaut en build) | Le proxy de Vite redirige `/api` vers `VITE_API_URL` (défaut `http://localhost:8000`). |

Exemple : `VITE_USE_MOCKS=false VITE_API_URL=http://localhost:8000 npm run dev`. Voir `.env.example`.

Dans le mock, toute `POST /api/auth/verify` avec un token non vide ouvre une session (`demo@example.org`).

## Structure

- `src/api/` — client typé (`client.ts`, `ApiError` avec `status`, `isUnauthorized`, `isRateLimited`, `retryAfter`), types du contrat, hooks TanStack Query.
- `src/components/` — `Layout` (en-tête, navigation, bouton fixe mobile), `AccountMenu`, `Placeholder`.
- `src/pages/` — pages provisoires (titre + emplacement), chargées à la demande sauf la home.
- `mocks/` — API simulée.

## Docker

`web/Dockerfile` construit le site statique et le sert avec nginx (port 80) ; `nginx.conf` proxifie `/api/` vers `http://api:8000` et gère le repli SPA.

```sh
docker build -t citizen-news-web web
```

Snippet à ajouter à `docker-compose.yml` (le service `api` doit exister sous ce nom) :

```yaml
  web:
    build: ./web
    depends_on:
      - api
    ports:
      - "8080:80"
```
