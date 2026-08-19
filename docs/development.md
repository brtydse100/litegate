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

Run backend tests:

```bash
cd backend
python -m pytest
```

Build and audit the production frontend:

```bash
cd frontend
npm run build
npm audit --omit=dev
```

Authorization tests should preserve the core boundary: normal portal users and
LiteLLM-key identities cannot bulk-edit keys, while administrators and the
management API identity can.

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
|-- API.md                 API examples and authorization
`-- DEPLOYMENT.md          Docker and Kubernetes operations
```

## Technology

- FastAPI, Pydantic, HTTPX, PyJWT, and SQLite
- React, TypeScript, Vite, TanStack Query, and Tailwind CSS
- Nginx and Uvicorn
- Docker Compose and Kubernetes with Helm

## Runtime behavior worth preserving

- The dashboard derives its access snapshot from key records instead of loading
  raw spend logs during ordinary page loads.
- Installation-wide keys are fetched lazily and paginated for administrators.
- New key secrets are displayed only when created.
- Bulk updates report per-key success or failure and use bounded concurrency.
- Local account role and active state are rechecked for authenticated requests.

For endpoint contracts, use the deployed OpenAPI document or [API.md](../API.md).
