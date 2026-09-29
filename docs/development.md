# Development guide

LiteGate combines a FastAPI backend with a React, TypeScript, and Vite frontend.
The production image serves static frontend assets through Nginx and proxies
`/api` to Uvicorn.

## Local environment

Install backend dependencies and start the API:

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal, install frontend dependencies and start Vite:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to port
`8000`. Copy [`.env.example`](../.env.example) or provide the required settings
through the environment before starting the backend.

## Checks

Check backend formatting and run its regression suite:

```bash
ruff format --check --diff backend
cd backend
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=75
```

Lint, format-check, type-check, build, and audit the production frontend:

```bash
cd frontend
npm run lint
npm run format:check
npm run typecheck
npm test
npm run test:e2e:smoke
npm run build
npm audit --omit=dev
```

GitHub Actions runs pytest with the established coverage floor, the frontend
unit suite, a short Playwright smoke flow, a real LiteLLM compatibility suite,
static checks, the production build, dependency audit, Helm lint,
documentation/version checks, and an all-in-one container build on every pull
request and push to `main`. The complete browser suite runs nightly and can also
be started manually.

## LiteLLM integration environment

The production Compose file intentionally connects to an existing LiteLLM
deployment. A separate opt-in stack provides disposable LiteLLM and PostgreSQL
services for compatibility testing:

```bash
docker compose -f deploy/docker-compose/docker-compose.integration.yml up -d --wait
```

If port `4000` is already in use, set `LITELLM_INTEGRATION_PORT` and use the
matching port in `LITELLM_URL` when running the tests.

The images are pinned by immutable multi-architecture digest. With the backend
development dependencies and frontend packages installed, run both live layers:

```bash
cd backend
RUN_LITELLM_INTEGRATION=1 \
LITELLM_URL=http://127.0.0.1:4000 \
LITELLM_MASTER_KEY=sk-litegate-integration-master \
JWT_SECRET=litegate-integration-jwt-secret-at-least-32-characters \
python -m pytest tests/integration/test_litellm_live.py -v

cd ../frontend
npx playwright test --config playwright.integration.config.ts
```

Stop the disposable services and remove their database afterward:

```bash
docker compose -f deploy/docker-compose/docker-compose.integration.yml down --volumes
```

## Project layout

```text
litegate/
|-- backend/
|   |-- app/routers/       Portal and v1 API routes
|   `-- app/services/      LiteLLM, OIDC, and local-user services
|-- frontend/              React, TypeScript, Vite, and Tailwind CSS
|-- deploy/
|   |-- docker-compose/    Single-server deployment
|   `-- helm/litegate/     Kubernetes Helm chart
|-- docs/                  Focused project guides and images
|-- scripts/               Version, release, and documentation checks
|-- API.md                 API examples and authorization
`-- DEPLOYMENT.md          Docker and Kubernetes operations
```

`VERSION` is the release version source of truth. Run
`python scripts/version.py --check` before publishing, or
`python scripts/version.py --set X.Y.Z` to update the package and Helm
references together. The only supported production image is defined by
`deploy/docker-compose/Dockerfile`; local development uses Uvicorn and Vite.

Release tags must use stable SemVer as `vX.Y.Z`, match `VERSION`, point to a
commit contained in `main`, and have notes at `docs/releases/vX.Y.Z.md`. Pushing
the tag runs one ordered release workflow: it publishes the multi-architecture
GHCR image as `X.Y.Z` and `sha-*`; adds `X.Y` and `latest` only if the tag points
to the current `main` commit after the build; verifies a normal Docker
pull/save/load round trip; and only then creates the GitHub Release. Shared
tags are promoted from the verified image digest in a serialized job. A failed
image publication therefore cannot produce a successful release without its
container package.

Manual runs are for pre-release testing. Their optional image tag must start
with `test-` or `dev-`, so they cannot replace stable release tags. A manual run
may update `latest` only when it is run from the current `main` commit. Image
publication for the same Git ref is serialized.

## Technology

- FastAPI, Pydantic, HTTPX, PyJWT, and SQLite
- React, TypeScript, Vite, TanStack Query, and Tailwind CSS
- Nginx and Uvicorn
- Docker Compose and Kubernetes with Helm

## Runtime behavior worth preserving

- The dashboard derives its access snapshot from key records instead of loading
  raw spend logs during ordinary page loads.
- Installation-wide keys are fetched lazily and paginated for administrators.
- Key secrets are displayed only when created unless optional API key storage is enabled; stored keys can be revealed by their owner or an administrator.
- Bulk updates report per-key success or failure and use bounded concurrency.
- Local account role and active state are rechecked for authenticated requests.
- SQLite stores local users and audit events, while operation cooldown state is
  in process. Production therefore runs exactly one replica; the Helm chart
  rejects larger replica counts until shared stores are implemented.

For endpoint contracts, use the deployed OpenAPI document or [API.md](../API.md).
