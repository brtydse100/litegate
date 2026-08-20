# LiteGate — Deployment Guide

LiteGate is a self-hosted portal that lets your team generate and manage their own LiteLLM API keys through a simple one-click interface. It ships as **a single Docker image** containing both the React frontend and the FastAPI backend.

---

## How it works

```
Browser → host port 80 → nginx (container port 8080)
              ├── /api/* → FastAPI backend (internal port 8000)
              └── /*     → React frontend (static files)
```

Everything runs in one container. You point it at your existing LiteLLM instance.

---

## Method 1 — Docker Compose (recommended for local/single-server)

### Prerequisites
- Docker Desktop (Windows/Mac) or Docker Engine + Compose (Linux)
- A running LiteLLM proxy (can be on the same machine or a remote server)

### Step 1 — Edit config.yaml

```bash
cd deploy/docker-compose
```

Open `config.yaml` and fill in your values:

```yaml
litellm_master_key: "sk-your-litellm-master-key"   # required
jwt_secret: "any-random-string-at-least-32-chars"   # required

litellm_url: "http://host.docker.internal:4000"     # local LiteLLM on same machine
# litellm_url: "http://192.168.1.100:4000"          # remote LiteLLM

# Admin account (remove in production, or change the password)
local_auth_username: "admin"
local_auth_password: "changeme"

# SSO — fill in to enable, leave blank to use only the local account
oidc_issuer_url: ""
oidc_client_id: ""
oidc_client_secret: ""
oidc_redirect_uri: "http://localhost/api/auth/callback"

# Optional: map ID-token groups to existing LiteLLM team IDs
oidc_groups_claim: "groups"
oidc_group_team_mapping:
  Engineering: "team-engineering"
oidc_require_team_mapping: false

root_url: "http://localhost"
```

### Step 2 — Pull the package and start

The `linux/amd64` release image is published to GitHub Container Registry. The
image Compose file defaults to `latest`; set `LITEGATE_VERSION` to pin a release.
Other architectures can use the local build path below.

```bash
docker compose -f docker-compose.image.yml up -d
```

To build locally from the checked-out source instead:

```bash
docker compose up --build
```

The portal opens at **http://localhost**.

### Step 3 — Stopping and updating

```bash
# Stop
docker compose down

# Pull code changes then rebuild
docker compose up --build
```

### Upgrading an existing data volume to 2.4+

LiteGate 2.4 runs as the unprivileged user `10001:10001`. Fresh volumes are
ready automatically. A volume first created by LiteGate 2.3 or earlier may be
owned by root; migrate it once before starting the new image:

```bash
docker compose -f docker-compose.image.yml run --rm --user 0 \
  --entrypoint chown litegate -R 10001:10001 /app/backend/data
docker compose -f docker-compose.image.yml up -d
```

The container listens on port `8080`; the supplied Compose mapping keeps the
browser URL on host port `80`.

### Offline usage

Once built, the image contains everything it needs:
- No internet access is required at runtime
- All fonts are system fonts (no CDN calls)
- LiteLLM runs inside your network

**Transferring the image to an air-gapped machine:**

```bash
# On the build machine — save the image to a tar file
docker save litegate-litegate:latest -o litegate.tar

# Copy litegate.tar to the target machine (USB, SCP, etc.)

# On the target machine — load the image
docker load -i litegate.tar

# Then start normally (no --build needed)
docker compose up
```

If your build machine has no internet, pre-pull the base images first:

```bash
docker pull node:20-alpine
docker pull python:3.12-slim
docker compose up --build
```

---

## Method 2 — Kubernetes / Helm

### Prerequisites
- Helm 3
- A LiteLLM instance reachable from inside the cluster (e.g. `http://litellm-svc.default:4000`)

### Step 1 — Build and push the image

```bash
docker build -f deploy/docker-compose/Dockerfile -t your-registry.io/litegate:2.4.0 .
docker push your-registry.io/litegate:2.4.0
```

### Step 2 — Install

```bash
helm install litegate ./deploy/helm/litegate \
  --set image.repository=your-registry.io/litegate \
  --set image.tag=2.4.0 \
  --set config.litellmUrl=http://litellm-svc:4000 \
  --set config.litellmMasterKey=sk-your-key \
  --set config.jwtSecret=$(openssl rand -base64 32) \
  --set config.oidcIssuerUrl=https://accounts.google.com \
  --set config.oidcClientId=YOUR_CLIENT_ID \
  --set config.oidcClientSecret=YOUR_CLIENT_SECRET \
  --set config.oidcRedirectUri=https://portal.example.com/api/auth/callback \
  --set config.rootUrl=https://portal.example.com \
  --set ingress.hosts[0].host=portal.example.com \
  --set ingress.enabled=true
```

### Step 3 — Upgrade after changes

```bash
helm upgrade litegate ./deploy/helm/litegate --reuse-values --set image.tag=2.4.0
```

### SSO roles and LiteLLM teams in Helm

The chart exposes the SSO role and team settings under `config`. Put them in a
private values file rather than trying to express the team map with repeated
`--set` flags:

```yaml
config:
  oidcGroupsClaim: "groups"

  # LiteGate role mapping: these users can manage local users and bulk-edit keys.
  adminGroups: "Platform Admins,AI Operations"

  # LiteLLM membership/key mapping: values are existing team IDs, not aliases.
  oidcGroupTeamMapping:
    Engineering: "team-engineering"
    AI-Platform:
      - "team-platform"
      - "team-shared-services"
  oidcRequireTeamMapping: true
```

Apply it with:

```bash
helm upgrade --install litegate ./deploy/helm/litegate \
  --namespace litegate --create-namespace \
  --values values.production.yaml
```

`adminGroups` controls the LiteGate `admin` role only. It does not grant the
LiteLLM team-admin role. `oidcGroupTeamMapping` adds the user as a regular
LiteLLM team member and assigns the first matched team to newly generated or
regenerated keys. Both settings read from `oidcGroupsClaim`, use
case-insensitive group-name matching, and support dotted claim paths.

The chart's default pod and container security contexts enforce the image's
non-root UID/GID, drop all capabilities, prevent privilege escalation, apply the
runtime-default seccomp profile, and use `fsGroup: 10001` for the data volume.

---

## Authentication options

### SSO (OIDC)

Works with any standard OIDC provider — Google, Azure AD, Okta, Keycloak, etc.

What to register with your identity provider:
- **Redirect URI:** `https://<your-domain>/api/auth/callback`
- **Grant type:** Authorization Code
- **Scopes:** `openid email profile`

Provider issuer URLs:
| Provider | Issuer URL |
|---|---|
| Google | `https://accounts.google.com` |
| Azure AD | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| Okta | `https://<domain>.okta.com/oauth2/default` |
| Keycloak | `https://<host>/realms/<realm>` |

#### Map SSO groups to LiteLLM teams

Use `oidc_group_team_mapping` to add users to existing LiteLLM teams when they
sign in. Values can be a single team ID or a list:

```yaml
oidc_groups_claim: "groups" # dotted paths such as realm_access.roles also work
oidc_group_team_mapping:
  Engineering: "team-engineering"
  AI-Platform:
    - "team-platform"
    - "team-shared-services"
oidc_require_team_mapping: false
```

Group matching is case-insensitive. Sync is additive: LiteGate adds all matched
memberships but does not automatically remove old ones, because LiteLLM member
removal can delete that member's team keys. The first matched team in
configuration order is applied to newly created or regenerated keys, enabling
LiteLLM's team model and budget policy. Existing keys need regeneration or an
administrator update. All mapped teams must already exist, and a mapping or
membership error fails login. Set `oidc_require_team_mapping: true` to also deny
users who have no mapped group.

### Local admin account

Set `local_auth_username` and `local_auth_password` in `config.yaml`. Both the SSO button and the local login form are shown simultaneously when both are configured.

**Remove the local account in production** by deleting those two lines from `config.yaml`.

---

## Key settings

All API keys generated through the portal share the same policy, set in `config.yaml`:

```yaml
key_max_budget: 10.0          # max spend per key in USD
key_budget_duration: "30d"    # budget resets every 30 days
key_models:                   # restrict to these models (YAML list)
  - gpt-4
  - gpt-3.5-turbo
key_duration: "90d"           # key expires after 90 days
key_tpm_limit: 100000         # tokens per minute
key_rpm_limit: 1000           # requests per minute
```

Leave any line commented out to use LiteLLM's defaults.

When a user regenerates a key, LiteGate transfers the old key's accumulated
spend to the replacement. The configured per-key budget therefore cannot be
reset through rotation. User and team budgets in LiteLLM remain recommended as
shared ceilings across all credentials and tools.

---

## Logo

Place your logo file in `frontend/public/` (e.g. `frontend/public/logo.svg`) then set in `config.yaml`:

```yaml
logo_url: "/logo.svg"
```

You can also use an external URL. When `logo_url` is blank, a dashed **"Your Logo Here"** placeholder is shown so you know exactly where the logo will appear. The logo is displayed with a preserved aspect ratio so it will never be stretched.

---

## Support ticket button

If you have a Jira/ServiceNow form for LLM Ops requests, set:

```yaml
support_ticket_url: "https://jira.example.com/create-ticket"
```

A visible "Open Support Ticket" button will appear next to the "Open LiteLLM Hub" button.

---

## Configuration reference

All `config.yaml` keys map directly to environment variables (uppercased). You can use either — environment variables take precedence.

| config.yaml key | Environment variable | Default | Description |
|---|---|---|---|
| `litellm_master_key` | `LITELLM_MASTER_KEY` | *(required)* | LiteLLM master key |
| `litellm_url` | `LITELLM_URL` | `http://localhost:4000` | LiteLLM proxy URL |
| `jwt_secret` | `JWT_SECRET` | *(required)* | Session token secret (≥32 chars) |
| `root_url` | `ROOT_URL` | `http://localhost` | Portal public URL (used for SSO redirect) |
| `oidc_issuer_url` | `OIDC_ISSUER_URL` | `""` | OIDC provider URL (blank = SSO disabled) |
| `oidc_client_id` | `OIDC_CLIENT_ID` | `""` | OIDC client ID |
| `oidc_client_secret` | `OIDC_CLIENT_SECRET` | `""` | OIDC client secret |
| `oidc_redirect_uri` | `OIDC_REDIRECT_URI` | `""` | Callback URI registered with IdP |
| `oidc_group_team_mapping` | `OIDC_GROUP_TEAM_MAPPING` | `{}` | SSO group to existing LiteLLM team ID or team-ID list; environment form is JSON |
| `oidc_require_team_mapping` | `OIDC_REQUIRE_TEAM_MAPPING` | `false` | Deny SSO login when no team mapping matches |
| `local_auth_username` | `LOCAL_AUTH_USERNAME` | `""` | Admin username (blank = disabled) |
| `local_auth_password` | `LOCAL_AUTH_PASSWORD` | `""` | Admin password |
| `logo_url` | `LOGO_URL` | `""` | Logo image URL or path |
| `litellm_ui_url` | `LITELLM_UI_URL` | `""` | LiteLLM web UI URL (adds hub button) |
| `support_ticket_url` | `SUPPORT_TICKET_URL` | `""` | Support ticket URL |
| `key_max_budget` | `KEY_MAX_BUDGET` | `null` | Budget per key (USD) |
| `key_budget_duration` | `KEY_BUDGET_DURATION` | `null` | Budget reset period |
| `key_models` | `KEY_MODELS` | `"[]"` | YAML list or JSON array of allowed models |
| `key_tpm_limit` | `KEY_TPM_LIMIT` | `null` | Tokens per minute |
| `key_rpm_limit` | `KEY_RPM_LIMIT` | `null` | Requests per minute |
| `key_duration` | `KEY_DURATION` | `null` | Key TTL |
| `key_team_id` | `KEY_TEAM_ID` | `""` | Fallback team for keys without an SSO-mapped primary team |
| `local_users_enabled` | `LOCAL_USERS_ENABLED` | `true` | Enable admin-created local accounts |
| `local_users_db_path` | `LOCAL_USERS_DB_PATH` | `data/litegate.db` | SQLite account database path |
| `admin_emails` | `ADMIN_EMAILS` | `""` | Comma-separated SSO administrator emails |
| `management_api_key` | `MANAGEMENT_API_KEY` | `null` | Optional admin credential for `/api/v1` via `X-API-Key` |
| `admin_groups` | `ADMIN_GROUPS` | `""` | Comma-separated SSO groups that receive admin access |
| `oidc_groups_claim` | `OIDC_GROUPS_CLAIM` | `groups` | ID-token group claim path; dot notation is supported |
| `oidc_scopes` | `OIDC_SCOPES` | `openid email profile` | OIDC scopes requested during login |

## Local users and persistence

Sign in with the bootstrap local administrator or an SSO account listed in `admin_emails`, then open the **Users** tab. Local accounts are stored with salted password hashes in SQLite.

To grant admin access by SSO group, set `admin_groups` and point `oidc_groups_claim` at the claim in your provider's ID token. Examples: `groups` for a flat group claim or `realm_access.roles` for Keycloak realm roles. If the provider requires a groups scope, add it to `oidc_scopes`. Group matching is case-insensitive. Providers that return group-overage references instead of group names must be configured to emit the required group directly in the ID token.

Docker Compose persists the database in the `litegate-data` named volume. The Helm chart creates a 1 Gi persistent volume claim by default; set `persistence.existingClaim` to reuse an existing claim, or set `persistence.enabled=false` only if local-account persistence is not needed.

## Automation API

Open `/api/docs` for interactive OpenAPI documentation. The stable routes are under `/api/v1`; see [API.md](API.md) for credential options, bulk key updates, and user-management examples.
