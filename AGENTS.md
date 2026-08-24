# AGENTS.md

This file provides guidance to coding agents working in this repository.

## Before any work

- **Never start coding immediately.** First ask the user clarifying questions, then present a plan and get their approval. Only implement after the plan is agreed.
- If the task seems trivial and you think planning is overkill, say so and propose a one-line plan, but still wait for the user's go-ahead.

## Bugs

- **Never just apply a fix.** Explain the root cause first and let the user decide how to proceed. Diagnosis before surgery.

## Before presenting work

- Run `format`, `lint`, and `typecheck` (see **Commands**; the backend has formatting only); fix all violations before showing the user anything. Never fix a violation by disabling a rule.


## Scope & Code Change Policy

- Don't refactor, rename, or "improve" code the user didn't ask you to touch. Never change behavior that was not explicitly requested.
- Keep all changes as minimal as possible unless explicitly asked for more. Prefer the simplest solution that works.
- **Never add a dependency without asking the user first**: present what it does, why hand-rolling is worse, and its cost. Read [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md) before proposing new dependencies, services, or persistent state: weigh every such change against its pillars.
- Apply DRY principles where possible.
- Python files must not exceed 400 lines.

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

## Releases

- Every LiteGate release must also update the project/package version using
  `scripts/version.py`, which keeps `VERSION`, frontend package metadata, and
  Helm release references synchronized.
- Use stable SemVer (`X.Y.Z`). For a big change, increment the minor version and
  reset the patch version: `X.Y.Z` -> `X.(Y+1).0`. For a small change, increment
  only the patch version: `X.Y.Z` -> `X.Y.(Z+1)`.
- Write GitHub Release notes in the LiteLLM release style, not merely "same as
  LiteLLM." Start with `## What's Changed`, then list each included change as a
  concise bullet using its conventional-commit type and scope (for example,
  `feat(auth): add OIDC group mapping` or `fix(keys): prevent duplicate key
  names`). Each bullet must identify the contributor and link the associated PR
  or issue when one exists. Include an exhaustive, traceable list of changes;
  do not replace it with a high-level summary. Add release-specific operational
  instructions only when relevant, such as image-signature verification.

## Repository layout

- `backend/app/`: FastAPI application, routes, configuration, and services.
- `frontend/src/`: React and TypeScript application.
- `deploy/docker-compose/`: Single-server image and Compose deployment.
- `deploy/helm/litegate/`: Kubernetes Helm chart.
- `frontend/src/demo/`: Browser-only mock API for the interactive GitHub Pages
  demo; it must not require credentials or a live backend.
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
- The public demo builds the real frontend with `VITE_DEMO_MODE=true` and uses
  synthetic content only. Never connect it to a real backend or embed secrets.
