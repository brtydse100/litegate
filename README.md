# LiteGate

![LiteGate — users entering a secure gateway and receiving managed AI API keys](docs/litegate-hero.png)

LiteGate is a lightweight, self-hosted portal and automation API for managing [LiteLLM](https://github.com/BerriAI/litellm) virtual keys. Users can obtain and manage their own key, while administrators control accounts, roles, limits, budgets, and key policies.

The dashboard stays fast on busy installations because it does **not** download raw spend logs during normal page loads. It renders a compact access snapshot from the key records already returned by LiteLLM. Administrative key lists are loaded only when needed and are paginated.

## Features

### Fast self-service key portal

- Create a LiteLLM virtual key with one click.
- Reveal a newly created secret once, with a dedicated copy action.
- Display masked identifiers, allowed models, expiration, spend, budget, TPM, and RPM.
- Regenerate a key with confirmation; the old key stops working immediately.
- Apply configurable models, budget, reset interval, duration, TPM, RPM, and team defaults.
- Link to a support system or the LiteLLM model hub.
- Avoid expensive raw spend-log requests on the main dashboard.

### SSO and local users

- Generic OpenID Connect support for Google, Microsoft Entra ID, Okta, Keycloak, and other compliant providers.
- Administrator assignment by SSO email address or group membership.
- Configurable group claim paths, including nested claims such as `realm_access.roles`.
- A bootstrap local administrator for setup and recovery.
- Administrator-created local accounts when SSO is unavailable or inappropriate.
- `user` and `admin` roles, password resets, and enable/disable controls.
- Immediate local-session revocation when an account is disabled.

### Bulk key administration

- Checkbox-based, paginated selection for administrators.
- Select individual keys or an entire page in a few clicks.
- Manual key-ID entry when a key is not on the current page.
- Edit only the fields supplied; untouched settings remain unchanged.
- Change aliases, models, budgets, reset intervals, TPM/RPM, duration, and blocked status.
- Update up to 100 keys per API request with bounded concurrency and per-key results.
- Regular users can update only their keys; LiteLLM-key authentication can update only that exact key.

### API and automation agents

- Stable automation endpoints under `/api/v1`.
- Swagger UI at `/api/docs`, ReDoc at `/api/redoc`, and OpenAPI JSON at `/api/openapi.json`.
- Authentication using a portal JWT, an optional management API key, or a LiteLLM virtual key.
- Paginated administrator key listing, key creation, and bulk policy updates.
- Local-user creation, listing, role changes, password resets, and enable/disable operations.
- A management API credential for trusted automation agents—no shared human password required.
- Partial bulk-update failures are reported individually instead of being hidden.

### Deployment and operations

- Docker Compose deployment with Nginx, React, and FastAPI.
- Persistent Docker storage for local accounts.
- Kubernetes deployment with the included Helm chart and optional PVC.
- YAML configuration with environment-variable overrides.
- Health endpoint at `/api/health`.
- Custom logo, LiteLLM model-hub link, and support-ticket link.

## How it works

```text
Human users / automation agents
              │
              ▼
      LiteGate (React + FastAPI)
         ├── OIDC provider
         ├── SQLite local-user store
         └── LiteLLM management API
                     │
                     ▼
             LiteLLM virtual keys
```

LiteGate is a focused access layer, not a replacement for LiteLLM. LiteLLM remains responsible for virtual keys, models, budgets, usage, and request routing.

## Quick start with Docker Compose

Requirements: Docker with Compose, a reachable LiteLLM instance, and its master key.

```bash
git clone https://github.com/brtydse100/litegate.git
cd litegate/deploy/docker-compose
```

Edit `config.yaml`:

```yaml
litellm_url: "http://host.docker.internal:4000"
litellm_master_key: "sk-your-litellm-master-key"
jwt_secret: "replace-with-a-long-random-secret"

# Bootstrap administrator; replace before first use.
local_auth_username: "admin"
local_auth_password: "replace-with-a-strong-password"

root_url: "http://localhost"
```

Start LiteGate:

```bash
docker compose up --build
```

Open [http://localhost](http://localhost). Local accounts are persisted in the `litegate-data` Docker volume. See [DEPLOYMENT.md](DEPLOYMENT.md) for production, offline, update, and Helm instructions.

## Users tab: purpose and use cases

The administrator-only **Users** tab manages people who need LiteGate access without SSO. It is useful for:

- onboarding a contractor or teammate who is not in your identity provider;
- providing temporary access during an SSO outage or migration;
- maintaining a controlled break-glass administrator;
- testing roles before connecting production SSO; and
- disabling local access immediately when it is no longer required.

Choose the role according to what the person needs:

| Role | Capabilities |
| --- | --- |
| `user` | Sign in, create or regenerate a personal key, view its access snapshot, and edit only owned keys |
| `admin` | Everything a user can do, plus manage local users, view paginated installation keys, create keys for others through the API, and bulk-edit any key |

The tab's actions reset passwords, promote or demote roles, and disable or enable accounts. Disabling an account invalidates its existing portal session on the next request.

Automation should not use a shared local username and password. Configure `management_api_key` and give the trusted agent only the secret it needs to call `/api/v1`. The current implementation provides one installation-wide management credential; rotate it if it is exposed.

## Authentication and administrators

### Local accounts

Set `local_auth_username` and `local_auth_password` to enable the bootstrap administrator. That administrator can create additional accounts from the **Users** tab. Passwords are salted and hashed with PBKDF2-SHA256 using 310,000 iterations. SQLite uses WAL mode and is persisted by both included deployment methods.

### OpenID Connect SSO

Register this callback URL with your provider:

```text
https://litegate.example.com/api/auth/callback
```

```yaml
oidc_issuer_url: "https://login.example.com/realms/company"
oidc_client_id: "litegate"
oidc_client_secret: "replace-me"
oidc_redirect_uri: "https://litegate.example.com/api/auth/callback"
oidc_scopes: "openid email profile"
```

| Provider | Issuer URL pattern |
| --- | --- |
| Google | `https://accounts.google.com` |
| Microsoft Entra ID | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| Okta | `https://<domain>.okta.com/oauth2/default` |
| Keycloak | `https://<host>/realms/<realm>` |

### Assign administrators by email or SSO group

Values are comma-separated and matched case-insensitively:

```yaml
admin_emails: "owner@example.com,platform@example.com"
admin_groups: "Platform Admins,AI Operations"
oidc_groups_claim: "groups"
```

Nested claims are supported:

```yaml
admin_groups: "litegate-admins"
oidc_groups_claim: "realm_access.roles"
```

The provider must include the desired value in the ID token. If it emits group IDs, configure those IDs. If it emits group-overage references, configure the provider to include the required group directly. Add a provider-specific scope such as `groups` to `oidc_scopes` when needed.

## Key policy and bulk editing

Optional defaults for new keys:

```yaml
key_max_budget: 25.0
key_budget_duration: "30d"
key_models:
  - gpt-4o-mini
key_duration: "90d"
key_tpm_limit: 100000
key_rpm_limit: 100
key_team_id: "team-id"
```

Bulk edit from the portal:

1. Open **Bulk edit key settings**.
2. Select keys or choose **Select this page**.
3. Enter only the settings that should change.
4. Click **Update selected keys**.

The administrator list loads only when the editor opens and uses 25-key pages. The result reports how many updates succeeded or failed.

## API

### Authentication methods

| Credential | Header | Permissions |
| --- | --- | --- |
| Portal JWT | `Authorization: Bearer <portal-token>` | Owned keys, or administrator permissions when the role is `admin` |
| LiteLLM key | `Authorization: Bearer <litellm-key>` | Read and edit only that exact key |
| Management key | `X-API-Key: <management-key>` | Administrator automation access |

Enable trusted-agent access:

```yaml
management_api_key: "replace-with-a-long-random-secret"
```

### Endpoint summary

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/me` | Inspect the current API identity |
| `GET` | `/api/v1/keys` | List keys available to the caller |
| `GET` | `/api/v1/keys?all=true&page=1&size=50` | Paginated administrator key list |
| `POST` | `/api/v1/keys` | Create a virtual key |
| `PATCH` | `/api/v1/keys/bulk` | Update one or more keys |
| `GET` | `/api/v1/users` | List local users as an administrator |
| `POST` | `/api/v1/users` | Create a local user as an administrator |
| `PATCH` | `/api/v1/users/{username}` | Update a local user as an administrator |

Bulk-update example:

```bash
curl -X PATCH https://litegate.example.com/api/v1/keys/bulk \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "keys": ["key-1", "key-2"],
    "settings": {
      "models": ["gpt-4o-mini"],
      "max_budget": 25,
      "budget_duration": "30d",
      "rpm_limit": 100
    }
  }'
```

See [API.md](API.md) for more examples and authorization details.

## Configuration

Use `config.yaml` or environment variables. Environment variables take precedence and use uppercase names—for example, `management_api_key` becomes `MANAGEMENT_API_KEY`.

| Setting | Default | Purpose |
| --- | --- | --- |
| `litellm_url` | `http://localhost:4000` | LiteLLM management URL |
| `litellm_master_key` | required | LiteLLM administrator key |
| `jwt_secret` | required | Portal-session signing secret |
| `jwt_expire_minutes` | `1440` | Portal-session lifetime |
| `root_url` | `http://localhost` | Public LiteGate URL |
| `cors_origins` | local origins | Allowed browser origins |
| `local_auth_username` / `local_auth_password` | empty | Bootstrap administrator |
| `local_users_enabled` | `true` | Allow managed local users |
| `local_users_db_path` | `data/litegate.db` | SQLite database location |
| `admin_emails` | empty | SSO administrator emails |
| `admin_groups` | empty | SSO administrator groups |
| `oidc_groups_claim` | `groups` | Group claim; dot notation supported |
| `management_api_key` | empty | Trusted-agent administrator credential |
| `logo_url` | empty | Custom header logo |
| `litellm_ui_url` | empty | Model-hub link base URL |
| `support_ticket_url` | empty | Support link |

See the complete [configuration reference](DEPLOYMENT.md#configuration-reference) and the ready-to-edit [`config.yaml`](deploy/docker-compose/config.yaml).

## Security behavior

- Signed OIDC state values expire after ten minutes.
- OIDC ID tokens are verified for signing key, issuer, audience, and expiration.
- The portal token is returned in a URL fragment, keeping it out of Nginx access logs.
- Secret comparisons use constant-time comparison where applicable.
- Local accounts use salted PBKDF2-SHA256 and a dummy hash for unknown users.
- Local role and active state are rechecked on every authenticated request.
- Users cannot disable themselves or remove their own administrator role through the API.
- Key-changing operations are limited to five per identity per minute.
- Bulk updates use a five-request concurrency bound.
- Included Nginx configurations set CSP, anti-clickjacking, MIME-sniffing, and referrer headers.

Replace all sample secrets, deploy behind HTTPS, restrict configuration access, and back up the local-user database or persistent volume.

## Development and testing

Backend:

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` to port `8000`.

Run checks:

```bash
cd backend && python -m pytest
cd ../frontend && npm run build && npm audit --omit=dev
```

## Project structure

```text
litegate/
├── backend/                  FastAPI application and tests
│   ├── app/routers/         Portal and v1 API routes
│   └── app/services/        LiteLLM, OIDC, and local-user services
├── frontend/                 React, TypeScript, Vite, Tailwind CSS
├── deploy/
│   ├── docker-compose/      Single-server deployment
│   └── helm/litegate/       Kubernetes Helm chart
├── docs/                     Repository images
├── API.md                    API examples
└── DEPLOYMENT.md             Full deployment guide
```

## Technology

- FastAPI, Pydantic, HTTPX, PyJWT, and SQLite
- React, TypeScript, Vite, TanStack Query, and Tailwind CSS
- Nginx and Uvicorn
- Docker Compose and Kubernetes with Helm

## License

No open-source license has been selected yet. The repository is public, but normal copyright restrictions apply until a license is added.
