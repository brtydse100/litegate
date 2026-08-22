# LiteGate

![LiteGate - secure, managed access to AI API keys](docs/litegate-hero.png)

LiteGate gives people one simple page to create and manage their own governed
[LiteLLM](https://github.com/BerriAI/litellm) API key. Users do not need the
LiteLLM administrator dashboard, and administrators do not need to hand out the
master key.

## The user experience

- Sign in with SSO or a local account.
- Click once to create a personal key and copy it.
- See the models, budget, spend and rate limits that apply.
- Regenerate a credential without resetting accumulated spend.
- Leave without loading the full LiteLLM administration or raw usage-log UI.

SSO groups can map users to existing LiteLLM teams automatically, so the key
inherits the intended team budget and model policy.

<details>
<summary><strong>Optional administrator and operations tools</strong></summary>

LiteGate also includes local-user management, team policy and member movement,
administrator-only bulk key editing, an automation API, audit history,
readiness checks, metrics, and verified backup/restore tooling. These controls
are kept out of the normal user's key page.

</details>

## Access model

| Capability | User | Administrator | Automation agent |
| --- | --- | --- | --- |
| Create, inspect, and regenerate a personal key | Yes | Yes | Via API |
| Manage local users and roles | No | Yes | Yes |
| List installation-wide keys | No | Yes | Yes |
| Bulk-edit key settings | **No** | **Yes** | **Yes** |
| Manage LiteLLM teams and move members | **No** | **Yes** | **Yes** |

Bulk key editing is administrator-only in both the UI and `/api/v1`. Trusted
agents authenticate with the installation-wide `management_api_key`; they do not
need a shared human password.

## How it works

```text
People / automation agents
            |
            v
   LiteGate (React + FastAPI)
      |-- OIDC provider
      |-- SQLite local-user store
      `-- LiteLLM management API
                    |
                    v
            LiteLLM virtual keys
```

LiteGate is an access layer, not a LiteLLM replacement. LiteLLM remains
responsible for virtual keys, models, budgets, usage, and request routing.

## Quick start with Docker Compose

Requirements: Docker with Compose, a reachable LiteLLM instance, and its master
key.

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

Start LiteGate from the prebuilt GitHub package:

```bash
docker compose -f docker-compose.image.yml up -d
```

This pulls the multi-architecture `ghcr.io/brtydse100/litegate:latest` package.
To pin a release, set `LITEGATE_VERSION`, for example
`LITEGATE_VERSION=2.5.0`. You can also build locally from source:

```bash
docker compose up --build
```

Open [http://localhost](http://localhost). Local accounts persist in the
`litegate-data` Docker volume. Replace every sample secret before using LiteGate
outside a local test environment.

## Documentation

| Guide | Contents |
| --- | --- |
| [Documentation index](docs/README.md) | Entry point for all guides |
| [Features and access model](docs/features.md) | User, admin, bulk-edit, and operational behavior |
| [Authentication](docs/authentication.md) | OIDC, local users, roles, and automation agents |
| [Configuration](docs/configuration.md) | Settings, environment variables, and key defaults |
| [Deployment](DEPLOYMENT.md) | Docker Compose, offline use, Kubernetes, and Helm |
| [API v1](API.md) | Authentication, key endpoints, bulk updates, and local users |
| [Development](docs/development.md) | Local setup, tests, architecture, and project layout |

Once deployed, interactive API documentation is available at `/api/docs`, with
ReDoc at `/api/redoc` and the OpenAPI document at `/api/openapi.json`.

## Security

LiteGate verifies OIDC token signatures and claims, uses browser-bound signed OIDC
state, keeps portal sessions in HttpOnly cookies, and stores local passwords as
salted PBKDF2-SHA256 hashes. Account status
and local roles are rechecked on authenticated requests. Key-changing operations
and administrative mutations are rate limited with disabled controls during
cooldowns, credential regeneration carries prior key spend, bulk updates use
bounded concurrency, and the included Nginx
configuration adds common browser security headers.

For production, use HTTPS, restrict access to configuration and secrets, rotate
the management API key if exposed, and back up the local-user database or volume.
See [Authentication and security](docs/authentication.md#security-behavior) for
the complete behavior and trust boundaries.

## Development and checks

```bash
cd backend && python -m pytest
cd ../frontend && npm test && npm run test:e2e && npm run build
```

See the [development guide](docs/development.md) for environment setup and local
development commands.

## License

[MIT](LICENSE)
