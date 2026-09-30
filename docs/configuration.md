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
| `jwt_previous_secrets` | empty | Comma-separated prior session secrets accepted only for verification during rotation |
| `jwt_algorithm` | `HS256` | Portal-session signing algorithm |
| `jwt_expire_minutes` | `1440` | Portal-session lifetime |
| `root_url` | `http://localhost` | Public LiteGate URL |
| `cors_origins` | local origins | Comma-separated browser origins |
| `oidc_issuer_url` | empty | OIDC provider; empty disables OIDC mode |
| `oidc_client_id` | empty | OIDC client ID |
| `oidc_client_secret` | empty | OIDC client secret |
| `oidc_redirect_uri` | empty | Registered callback URI |
| `oidc_scopes` | `openid email profile` | Space-separated requested scopes |
| `oidc_authorization_endpoint` | empty | Manual authorization endpoint; set with the token and JWKS endpoints to bypass discovery |
| `oidc_token_endpoint` | empty | Manual token endpoint; set with the authorization and JWKS endpoints |
| `oidc_jwks_uri` | empty | Manual signing-key endpoint; set with the authorization and token endpoints |
| `oidc_groups_claim` | `groups` | Group path in the verified ID token or generic UserInfo; dot notation supported |
| `oidc_group_team_mapping` | `{}` | SSO group to existing LiteLLM team ID or team-ID list |
| `oidc_require_team_mapping` | `false` | Deny SSO login when no configured team matches |
| `sso_default_team_id` | empty | Existing LiteLLM team added to every SSO user in addition to group-mapped teams |
| `inherit_litellm_admin` | `false` | Grant LiteGate admin access to a matching full LiteLLM `proxy_admin` |
| `admin_emails` | empty | Comma-separated SSO administrator emails |
| `admin_groups` | empty | Comma-separated SSO administrator groups |
| `local_auth_username` | empty | Bootstrap administrator username |
| `local_auth_password` | empty | Bootstrap administrator password |
| `local_users_enabled` | `true` | Allow administrator-created local accounts and show their administration page |
| `local_users_db_path` | `data/litegate.db` | SQLite account database path |
| `audit_retention_days` | `90` | Days to retain audit events before automatic cleanup |
| `audit_cleanup_batch_size` | `1000` | Maximum expired audit rows removed per new audit event |
| `management_api_key` | empty | Trusted-agent administrator credential for `/api/v1` |

The management key grants administrator access, including administrator-only
bulk key editing. It is not a user credential or a scoped token.

LiteLLM administrator status is used only when `inherit_litellm_admin` is
enabled. It recognizes the full `proxy_admin` role; read-only, organization, and
team administrator roles are not promoted to installation-wide LiteGate admin.
Otherwise, SSO administrators come from `admin_emails` or `admin_groups`, and a
local account must have LiteGate's `admin` role. Team mapping never grants
administrator access.

OIDC discovery is used by default. Providers that do not expose usable discovery
metadata can instead set all three manual endpoint settings. Partial manual
configuration is rejected at startup so login cannot silently mix modes.

### Generic OAuth SSO

Generic mode authenticates through the configured UserInfo endpoint using the
access token returned by the token endpoint. Configure all five required
credentials/endpoints and leave the OIDC issuer and manual endpoints blank.
Incomplete or conflicting configuration is rejected at startup. Provider and
callback URLs require HTTPS; HTTP is permitted only for localhost development.

| Setting | Default | Purpose |
| --- | --- | --- |
| `generic_client_id` | empty | Required OAuth client ID |
| `generic_client_secret` | empty | Required OAuth client secret |
| `generic_authorization_endpoint` | empty | Required authorization endpoint |
| `generic_token_endpoint` | empty | Required token endpoint |
| `generic_userinfo_endpoint` | empty | Required authenticated UserInfo endpoint |
| `generic_redirect_uri` | empty | Callback override; empty uses `root_url` + `/api/auth/callback` |
| `generic_scope` | `openid profile email` | Space-separated requested scopes |
| `generic_user_id_attribute` | `sub` | Stable user ID field in UserInfo; dot notation supported |
| `generic_user_email_attribute` | `email` | Email field in UserInfo; dot notation supported |
| `generic_client_use_pkce` | `false` | Enable PKCE with S256 |
| `generic_include_client_id` | `true` | Send client credentials in the token request body; `false` uses HTTP Basic |

These settings accept their uppercase `GENERIC_*` environment equivalents,
including LiteLLM's endpoint and user-attribute names. Environment variables
override YAML. `generic_redirect_uri` is LiteGate's callback override, and
`root_url` is its public base URL; LiteLLM's `PROXY_BASE_URL` is not used.

See [generic SSO setup](authentication.md#generic-oauth-sso) for a YAML example,
provider limitations, and the supported compatibility scope.

### Audit-history retention

Audit events are retained for 90 days by default. When LiteGate records a new
audit event, it removes up to `audit_cleanup_batch_size` events older than
`audit_retention_days` in the same SQLite transaction. This bounds cleanup work
while eventually removing expired history; if no audit events are written,
cleanup resumes on the next audit write. Use the verified SQLite backup
procedure in the [deployment guide](../DEPLOYMENT.md#backup-and-restore) before
the retention period when longer-term archival is required.

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

Set `sso_default_team_id` to add every SSO user to one existing LiteLLM team in
addition to their group-mapped teams. Group-mapped teams remain first in the
list and therefore take precedence as the primary team for generated keys; the
default team becomes primary only when no group matches.

Group names match case-insensitively. Membership sync is additive on login, and
the first matched team in configuration order becomes the primary team for new
or regenerated keys. Existing keys require regeneration or an administrator
update. Teams and their budget/model policy must already exist in LiteLLM. A
mapping error fails login; enabling `oidc_require_team_mapping` also rejects an
SSO user whose groups have no mapping. See
[Authentication and security](authentication.md#mapping-sso-groups-to-litellm-teams)
for lifecycle and removal behavior.

## Key defaults

### Optional API key storage

Key secrets are shown only at creation by default. Set `save_api_keys_in_db: true`
in Docker Compose's `config.yaml`, `SAVE_API_KEYS_IN_DB=true` as an environment
variable, or `config.saveApiKeysInDb: true` in Helm values to retain full API keys
in LiteGate's existing SQLite database (`local_users_db_path`). The default is
`false`.

When enabled, **Show API key** replaces **Regenerate key** for keys with a stored
copy. Owners can reveal their own keys, and administrators can reveal keys from
the installation key list. Keys created before enabling storage, or outside
LiteGate, have no recoverable copy; owners must regenerate them once to save a
replacement. Revealing a key does not rotate it or reset its spend.

Stored secrets are plaintext, so the database, its volume, and its backups contain
usable credentials. Keep the existing persistent volume and restrict access to
it and its backups. Disabling the setting stops saving and revealing keys but
does not erase previously stored copies. Deleting or regenerating a key through
LiteGate removes its stored copy; reveal requests also verify the key still
exists in LiteLLM. If SQLite cleanup fails after successful revocation, LiteGate
logs a warning and preserves the working replacement. A revoked copy can remain
in SQLite but cannot be revealed. Secrets are fetched only on demand, excluded from key listings
and audit events, and returned with `Cache-Control: no-store`.

### Generated-key policy

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

### Rotate the session secret without signing everyone out

Move the current value to `jwt_previous_secrets`, install a new random
`jwt_secret`, and restart LiteGate. New sessions use only the new secret while
existing sessions continue to verify with the prior value. After the configured
`jwt_expire_minutes` has elapsed, remove the prior value and restart again.
Never reuse a previous secret for signing new sessions.
