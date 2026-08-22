# LiteGate API v1

Interactive OpenAPI documentation is available at `/api/docs` on every LiteGate deployment. All v1 routes are under `/api/v1`.

## Authentication

Use one of these credentials:

1. The HttpOnly portal session cookie automatically used by the browser. Existing clients may also send a portal JWT as `Authorization: Bearer <portal-token>`.
2. A LiteLLM virtual key as `Authorization: Bearer <litellm-key>`. It can identify and inspect only itself; it cannot bulk-edit keys.
3. The optional `management_api_key` as `X-API-Key: <management-key>`. It has admin access and should be stored like a password.

Check the active identity:

```bash
curl https://litegate.example.com/api/v1/me \
  -H "Authorization: Bearer $TOKEN"
```

## Keys

List the authenticated portal user's keys:

```bash
curl https://litegate.example.com/api/v1/keys \
  -H "Authorization: Bearer $TOKEN"
```

Admins can list keys without loading the entire installation at once:

```bash
curl "https://litegate.example.com/api/v1/keys?all=true&page=1&size=50" \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

Add `search`, `team_id`, or `blocked=true|false` to scope the installation
before pagination. The same filters work on the identifier endpoint, so an
administrator can select every matching result without selecting unrelated
keys:

```bash
curl "https://litegate.example.com/api/v1/keys/identifiers?search=alice&blocked=false" \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

The bulk editor's explicit **Select all keys** action uses the identifier-only
administrator endpoint. It follows LiteLLM pagination server-side and returns at
most 5,000 identifiers:

```bash
curl https://litegate.example.com/api/v1/keys/identifiers \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

Create a key for the authenticated user:

```bash
curl -X POST https://litegate.example.com/api/v1/keys \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

An admin using `X-API-Key` can create a key for a specified user:

```bash
curl -X POST https://litegate.example.com/api/v1/keys \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"automation:ci","email":"ci@example.com"}'
```

Delete a key without placing the credential in the URL (where proxy logs could
capture it). A virtual key may delete itself; portal users may delete their own
keys; administrators and the management API may delete any key:

```bash
curl -X DELETE https://litegate.example.com/api/v1/keys \
  -H "Authorization: Bearer $TOKEN_OR_VIRTUAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"key":"sk-key-to-delete"}'
```

Bulk-edit key settings as an administrator. This endpoint requires an admin portal session or the management API key:

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

Supported bulk fields are `key_alias`, `models`, `max_budget`, `budget_duration`, `tpm_limit`, `rpm_limit`, `duration`, and `blocked`. A request can contain up to 5,000 unique keys. Updates run with bounded concurrency and return a result for every key, so partial failures are visible.

## Teams (admin only)

List teams with server-side pagination and optional search:

```bash
curl "https://litegate.example.com/api/v1/teams?page=1&size=25&search=platform" \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

Create a team and its budget/model policy:

```bash
curl -X POST https://litegate.example.com/api/v1/teams \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_alias":"Platform",
    "team_id":"team-platform",
    "models":["gpt-4o-mini"],
    "max_budget":250,
    "budget_duration":"30d",
    "rpm_limit":100,
    "blocked":false
  }'
```

Edit only the fields that should change:

```bash
curl -X PATCH https://litegate.example.com/api/v1/teams/team-platform \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_budget":300,"models":["gpt-4o-mini","claude-sonnet"]}'
```

Move a member and every key scoped to the source team:

```bash
curl -X POST https://litegate.example.com/api/v1/teams/team-research/members/move \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id":"user-bob",
    "destination_team_id":"team-platform",
    "confirm_policy_change":true
  }'
```

The move preserves the member's LiteLLM team role. LiteGate adds the destination
membership, migrates and verifies up to 500 source-team keys, then removes the
source membership. A failed key migration leaves the source membership in
place. Moves out of teams referenced by `oidc_group_team_mapping` or
`KEY_TEAM_ID` are rejected until configuration is changed.

Delete a team:

```bash
curl -X DELETE https://litegate.example.com/api/v1/teams/team-platform \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

Team management requires an administrator portal session or the management API
key. Supported policy fields are `team_alias`, `models`, `max_budget`,
`budget_duration`, `tpm_limit`, `rpm_limit`, and `blocked`; `team_id` can be set
only while creating a team. An empty `models` list means all models.

Deleting a team also deletes its LiteLLM team-scoped API keys. LiteGate refuses
to delete teams referenced by `oidc_group_team_mapping` or `KEY_TEAM_ID`; remove
the reference first and restart LiteGate with the new configuration.

## Local users (admin only)

List local users:

```bash
curl https://litegate.example.com/api/v1/users \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

Create a local user:

```bash
curl -X POST https://litegate.example.com/api/v1/users \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "username":"alice",
    "email":"alice@example.com",
    "password":"temporary-long-password",
    "role":"user"
  }'
```

Disable a user or reset a password:

```bash
curl -X PATCH https://litegate.example.com/api/v1/users/alice \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active":false}'
```

Local-user passwords use salted PBKDF2-SHA256 hashes. Disabling a local user invalidates existing portal sessions on their next request.

## Operations and audit (admin only)

Check LiteLLM connectivity and the writable local database:

```bash
curl https://litegate.example.com/api/v1/status \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

Read the latest secret-safe management events:

```bash
curl "https://litegate.example.com/api/v1/audit-events?limit=100" \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

Scrape low-cardinality Prometheus metrics. This endpoint is administrator-only;
configure the monitor to send the management key rather than putting it in the
URL. Metrics never include request headers, query strings, bodies, user IDs, or
key values.

```bash
curl https://litegate.example.com/api/v1/metrics \
  -H "X-API-Key: $LITEGATE_MANAGEMENT_KEY"
```

All API responses include `X-Request-ID`. A caller may supply a safe identifier
using the same header; LiteGate replaces malformed or overlong values. The
structured request log records that identifier, route template, method, status,
duration, and client address without logging credentials or request payloads.

Audit details redact credential-shaped fields and store only counts for bulk key
targets. Public probes are `GET /api/health/live` for process liveness and
`GET /api/health/ready` for LiteLLM plus database readiness; readiness returns
HTTP 503 when either dependency is unavailable.
