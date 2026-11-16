# Local Keycloak and LiteLLM validation

This disposable harness uses synthetic identities and credentials only. It binds
Keycloak and the modern LiteLLM test gateway to loopback. No real provider account,
production backend, Enterprise license, or global TLS override is required.

Use Python 3.12, Node.js 20.19+ or 22.12+, and Docker Compose with `!override` support.
The shell examples below use Bash line continuations; in PowerShell run each
Compose command on one line. From the repository root, install the existing
backend requirements, then start the isolated modern gateway and PostgreSQL:

```bash
python -m pip install -r backend/requirements-dev.txt
docker compose -p litegate-budget-compat \
  -f deploy/docker-compose/docker-compose.integration.yml \
  -f deploy/docker-compose/docker-compose.budget-integration.yml up -d --wait
docker compose -p litegate-sso-test \
  -f deploy/docker-compose/docker-compose.sso.yml up -d
```

The override pins LiteLLM 1.109.1 by digest on port 4001. It supplies a synthetic
mock model and the public integration master key; no inference provider is used.
Keycloak 26.8.2 is pinned by digest on port 8082. Wait for its realm discovery URL
to return 200:
`http://127.0.0.1:8082/realms/litegate-sso/.well-known/openid-configuration`.
Install existing frontend dependencies/browser tooling, then run:

```bash
cd frontend
npm ci
npx playwright install chromium
npx playwright test --config playwright.sso.config.ts
```

The runner starts the actual FastAPI backend on 8000 and Vite on 4176, seeds only
the dedicated loopback gateway, and imports the test organization hierarchy. It
uses the existing configuration/authentication code. No mock portal session or
patched OIDC verification is used. Ports must be free before starting the runner.
Use the pinned gateway without overriding `LITELLM_URL` for this reproduction.
The test backend persists its own SQLite file at
`backend/data/litegate-sso-test.db`, including across the tested restart.

Synthetic personas cover system administrator, designated group administrator,
child-group administrator, ordinary user, user with no key, outsider, designated
non-administrator, and undesignated administrator. LiteGate-managed group roles
allow the positive delegated tests without a native Enterprise team-admin role.
The optional `SSO_TEST_TEAM_ADMINISTRATION=true` fixture switch additionally
requires a legitimately licensed local gateway; it does not bypass licensing.

Tests check real signed-in role/API boundaries, invalid callback state, subtree
isolation, email copying, no-key directory discovery, original key identifier and
secret after login/restart/group transfer, and successful inference with that
original credential. Analytics isolation uses deliberately distinct synthetic
stored snapshots; aggregation correctness is tested separately in backend tests.

The helper can restart its own test backend through an ignored marker file.
It does not control production processes. Browser traces are disabled because
they could capture temporary authorization codes or synthetic key secrets.
The fixture's static passwords/client secret are test-only and explicitly public.
Normal backend state and test results stay ignored by Git.

Configuration and unit/API checks:

```bash
python -m unittest scripts/test_feature_configuration.py
cd backend
python -m pytest -q
```

Run the configuration check from the repository root with Helm installed. If
returning from the frontend commands above, first use `cd ..`.

Stop only these named test projects when finished. Removing their test volumes
also removes test databases; never use volume-deletion commands for a production
upgrade. Keep original operator volumes and unrelated running containers intact.
