# LiteGate API v1

Interactive OpenAPI documentation is available at `/api/docs` on every LiteGate deployment. All v1 routes are under `/api/v1`.

## Authentication

Use one of these credentials:

1. A portal session JWT as `Authorization: Bearer <portal-token>`.
2. A LiteLLM virtual key as `Authorization: Bearer <litellm-key>`. It can edit only itself.
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

Bulk-edit key settings:

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

Supported bulk fields are `key_alias`, `models`, `max_budget`, `budget_duration`, `tpm_limit`, `rpm_limit`, `duration`, and `blocked`. Updates run with bounded concurrency and return a result for every key, so partial failures are visible.

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
