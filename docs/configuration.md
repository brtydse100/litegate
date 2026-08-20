# Configuration reference

LiteGate reads `config.yaml` and environment variables. Environment variables
take precedence and use uppercase names; for example, `management_api_key`
becomes `MANAGEMENT_API_KEY`.

Start from [`deploy/docker-compose/config.yaml`](../deploy/docker-compose/config.yaml)
for Docker Compose or [`.env.example`](../.env.example) for local development.

## Core and authentication settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `litellm_url` | `http://localhost:4000` | LiteLLM proxy and management URL |
| `litellm_master_key` | required | LiteLLM administrator key |
| `jwt_secret` | required | Portal-session signing secret |
| `jwt_algorithm` | `HS256` | Portal-session signing algorithm |
| `jwt_expire_minutes` | `1440` | Portal-session lifetime |
| `root_url` | `http://localhost` | Public LiteGate URL |
| `cors_origins` | local origins | Comma-separated browser origins |
| `oidc_issuer_url` | empty | OIDC provider; empty disables SSO |
| `oidc_client_id` | empty | OIDC client ID |
| `oidc_client_secret` | empty | OIDC client secret |
| `oidc_redirect_uri` | empty | Registered callback URI |
| `oidc_scopes` | `openid email profile` | Space-separated requested scopes |
| `oidc_groups_claim` | `groups` | ID-token group path; dot notation supported |
| `oidc_group_team_mapping` | `{}` | SSO group to existing LiteLLM team ID or team-ID list |
| `oidc_require_team_mapping` | `false` | Deny SSO login when no configured team matches |
| `admin_emails` | empty | Comma-separated SSO administrator emails |
| `admin_groups` | empty | Comma-separated SSO administrator groups |
| `local_auth_username` | empty | Bootstrap administrator username |
| `local_auth_password` | empty | Bootstrap administrator password |
| `local_users_enabled` | `true` | Allow administrator-created local accounts |
| `local_users_db_path` | `data/litegate.db` | SQLite account database path |
| `management_api_key` | empty | Trusted-agent administrator credential for `/api/v1` |

The management key grants administrator access, including administrator-only
bulk key editing. It is not a user credential or a scoped token.

### SSO team mapping

Use a YAML object in `config.yaml`. A group may map to one existing LiteLLM team
or several:

```yaml
oidc_groups_claim: "realm_access.roles"
oidc_group_team_mapping:
  Engineering: "team-engineering"
  AI-Platform:
    - "team-platform"
    - "team-shared-services"
oidc_require_team_mapping: false
```

The equivalent environment variable is a JSON object on one line:

```bash
OIDC_GROUP_TEAM_MAPPING={"Engineering":"team-engineering","AI-Platform":["team-platform","team-shared-services"]}
OIDC_REQUIRE_TEAM_MAPPING=false
```

Group names match case-insensitively. Membership sync is additive on login, and
the first matched team in configuration order becomes the primary team for new
or regenerated keys. Existing keys require regeneration or an administrator
update. Teams and their budget/model policy must already exist in LiteLLM. A
mapping error fails login; enabling `oidc_require_team_mapping` also rejects an
SSO user whose groups have no mapping. See
[Authentication and security](authentication.md#mapping-sso-groups-to-litellm-teams)
for lifecycle and removal behavior.

## Key defaults

These values are applied when LiteGate creates a key. Leave an optional setting
unset to use the corresponding LiteLLM default.

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

| Setting | Default | Purpose |
| --- | --- | --- |
| `key_max_budget` | unset | Maximum spend per generated key |
| `key_budget_duration` | unset | Budget reset period, such as `30d` |
| `key_models` | `[]` | Allowed model names |
| `key_duration` | unset | Generated key lifetime, such as `90d` |
| `key_tpm_limit` | unset | Tokens-per-minute limit |
| `key_rpm_limit` | unset | Requests-per-minute limit |
| `key_team_id` | unset | Fallback LiteLLM team for generated keys without an SSO-mapped primary team |

Administrators can override supported settings later with the portal bulk editor
or `PATCH /api/v1/keys/bulk`. Normal users cannot bulk-edit keys. See
[Features and access model](features.md#administrator-only-bulk-editing).

Regeneration carries the accumulated spend from the old credential into its
replacement. This prevents users from refreshing a per-key allowance by rotating
the key. LiteLLM also tracks spend at user and team scope; configure those budgets
as an additional shared ceiling when a person may own keys outside LiteGate.

## Portal integration settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `logo_url` | empty | Header logo URL or served path |
| `litellm_ui_url` | empty | Browser-accessible LiteLLM model-hub link |
| `support_ticket_url` | empty | Support button destination |

To use a repository-hosted logo, place it in `frontend/public/` and set a served
path such as:

```yaml
logo_url: "/logo.svg"
```

## Minimal production-shaped example

```yaml
litellm_url: "https://litellm.internal.example"
litellm_master_key: "replace-me"
jwt_secret: "replace-with-at-least-32-random-characters"
root_url: "https://litegate.example.com"

oidc_issuer_url: "https://accounts.example.com"
oidc_client_id: "litegate"
oidc_client_secret: "replace-me"
oidc_redirect_uri: "https://litegate.example.com/api/auth/callback"

admin_groups: "litegate-admins"
oidc_group_team_mapping:
  Engineering: "team-engineering"
oidc_require_team_mapping: true
management_api_key: "replace-with-a-separate-long-random-secret"
```

Do not commit real credentials. Store configuration and secrets using the
controls appropriate to the deployment platform. Continue with
[Authentication and security](authentication.md) or the
[deployment guide](../DEPLOYMENT.md).
