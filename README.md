# LiteGate — Quick Reference

## What is this?
A self-hosted portal that lets your team generate their own LiteLLM API keys with one click.
Users can log in through SSO (Google, Azure, Okta, Keycloak) or with administrator-managed local accounts.

---

## Project structure

```
.
├── backend/                  Python (FastAPI) source code
│   ├── app/
│   ├── tests/
│   ├── requirements.txt
│   └── requirements-dev.txt  dev dependencies (pytest etc.)
├── frontend/                 React (Vite) source code
├── deploy/
│   ├── docker-compose/       Docker Compose deployment
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   ├── config.yaml       ← edit this before deploying
│   │   ├── nginx.conf
│   │   └── supervisord.conf
│   └── helm/
│       └── litegate/         Kubernetes Helm chart
└── README.md
```

---

## Deploy with Docker (recommended)

```bash
cd deploy/docker-compose
```

1. Edit `config.yaml` with your values (see below)
2. Run:
```bash
docker compose up --build
```
3. Open http://localhost

Works offline once built — no internet needed at runtime.

---

## Run locally (dev)

**Backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal)
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## deploy/docker-compose/config.yaml — the only file you need to edit

```yaml
# Required
litellm_master_key: "sk-..."        # your LiteLLM master key
jwt_secret: "random-32-char-string"

# Where is LiteLLM?
litellm_url: "http://host.docker.internal:4000"  # local machine
# litellm_url: "http://192.168.1.10:4000"        # remote server

# Local admin account (remove in production)
local_auth_username: "admin"
local_auth_password: "yourpassword"

# SSO — fill in to enable, leave blank to skip
oidc_issuer_url: ""
oidc_client_id: ""
oidc_client_secret: ""
oidc_redirect_uri: "http://localhost/api/auth/callback"
oidc_scopes: "openid email profile"
oidc_groups_claim: "groups"

# Administrator access (comma-separated, case-insensitive)
admin_emails: "admin@company.com"
admin_groups: "Platform Admins,AI Operations"

# Public URL of this portal (used for SSO redirect after login)
root_url: "http://localhost"

# Branding
logo_url: ""            # URL or /logo.svg (put file in frontend/public/)
litellm_ui_url: ""      # adds an "Open LiteLLM Hub" button

# Support ticket button
support_ticket_url: ""

# Key policy — applied to every generated key
# key_max_budget: 10.0
# key_budget_duration: "30d"
# key_models:
#   - gpt-4
#   - gpt-3.5-turbo
# key_duration: "90d"
```

---

## SSO setup (quick)

Register an OAuth app with your provider:
- **Redirect URI:** `http://your-domain/api/auth/callback`
- **Scopes:** `openid email profile`

| Provider  | oidc_issuer_url |
|-----------|----------------|
| Google    | `https://accounts.google.com` |
| Azure AD  | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| Okta      | `https://<domain>.okta.com/oauth2/default` |
| Keycloak  | `https://<host>/realms/<realm>` |

---

## Key alias
Keys are automatically named after the user — `alice@company.com` gets **"alice's key"**.

## Logo
Drop an image into `frontend/public/` and set in `config.yaml`:
```yaml
logo_url: "/logo.svg"
```
When `logo_url` is blank a dashed placeholder labelled **"Your Logo Here"** is shown so you can see exactly where the logo appears.

## Rebuild after config changes
```bash
cd deploy/docker-compose && docker compose up --build
```

## Restore dev dependencies after cloning
```bash
cd frontend && npm install
cd backend && pip install -r requirements-dev.txt
```

## Run backend tests
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

---

## LiteGate 2 features

- The dashboard no longer downloads raw spend logs. Its access snapshot is rendered from the already-loaded key record, keeping the home page responsive on busy installations.
- Admins can add, disable, promote, and reset local users from the **Users** tab. The configured `local_auth_username` remains the bootstrap administrator.
- SSO users can receive administrator access by email or group name. Configure `admin_groups` and, when needed, the provider-specific `oidc_groups_claim` and `oidc_scopes` values.
- Key policies can be bulk-edited in a few clicks: open **Bulk edit key settings**, select keys (or a whole page), enter only the values to change, and submit once. Non-admins are restricted to their own keys; a caller proving possession of a LiteLLM key can edit only that key.
- Interactive API documentation is served at `/api/docs`. See [API.md](API.md) for authentication and curl examples.

Local users are persisted automatically in the Docker Compose `litegate-data` volume. Back up this volume along with your configuration.
