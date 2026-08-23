# AGENTS.md

This file provides guidance to coding agents working in this repository.

## Project overview

LiteGate is a small, security-focused access layer for LiteLLM. It gives users a
self-service page for governed virtual keys and gives administrators narrowly
scoped user, team, key, audit, and operational controls. LiteLLM remains the
source of truth for models, budgets, spend, and request routing.

## Working agreements

- Keep changes focused on the request. Do not refactor unrelated code.
- Preserve the authorization boundary: ordinary users and LiteLLM-key identities
  cannot perform administrative or bulk-key operations.
- Never commit secrets, real API keys, passwords, tokens, or production URLs.
- Do not weaken authentication, CSRF protection, rate limits, security headers,
  or audit behavior to make a test pass.
- Do not add a runtime dependency without explaining why it is needed.
- Treat existing uncommitted changes as user work and do not overwrite them.
- Agents may inspect Git state and diffs, but must not commit or push unless the
  user explicitly requests it.

## Repository layout

- `backend/app/`: FastAPI application, routes, configuration, and services.
- `frontend/src/`: React and TypeScript application.
- `deploy/docker-compose/`: Single-server image and Compose deployment.
- `deploy/helm/litegate/`: Kubernetes Helm chart.
- `demo/`: Static GitHub Pages demo; it must not require credentials or a live
  backend.
- `docs/`: User and operator documentation plus demo media.
- `scripts/`: Release and documentation consistency checks.

## Commands

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm ci
npm run build
npm audit --omit=dev
npm run dev
```

The Vite development server runs on port 5173 and proxies `/api` to the backend
on port 8000.

### Repository checks

```bash
python scripts/version.py --check
python scripts/check_docs.py
helm lint deploy/helm/litegate
docker build -f deploy/docker-compose/Dockerfile -t litegate:local .
```

Run the checks relevant to the files changed. Before handing off a cross-cutting
or release-related change, run the full CI-equivalent set when the local tooling
is available.

## Architecture and invariants

- The browser uses an HttpOnly session cookie for portal access. The management
  API uses its own installation-wide credential.
- OIDC token signatures and claims are verified; local passwords are salted and
  hashed. Account role and active state are rechecked on authenticated requests.
- A newly created key secret is shown only in its creation response.
- Normal dashboard loads use key metadata rather than raw spend-log scans.
- Administrative key listing is lazy and paginated; bulk work uses bounded
  concurrency and reports per-item failures.
- SQLite stores local users and audit events. Cooldown and related operational
  state is process-local, so production is intentionally single-replica.
- Configuration is defined in `backend/app/config.py`. Keep `.env.example`,
  `docs/configuration.md`, deployment examples, and tests synchronized when a
  setting changes.
- `VERSION` is the release source of truth. Use `scripts/version.py` for version
  changes rather than editing generated references independently.

## Documentation expectations

- Update `API.md` when public endpoint contracts or authorization change.
- Update the focused guide under `docs/` when configuration, authentication,
  deployment, testing, or visible behavior changes.
- Keep root `README.md` concise and route detail into the focused guides.
- The public demo is intentionally static and read-only. Use synthetic content
  only, and keep its links and media paths compatible with the `/litegate/`
  GitHub Pages base path.
