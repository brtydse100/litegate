# Lock down key creation in LiteLLM

LiteGate's budgets and policies apply to the keys LiteGate creates. LiteLLM's
default `internal_user` role also lets a person create keys themselves, through
the LiteLLM Admin UI or by calling `/key/generate` with the key LiteGate gave
them. Those keys have no LiteGate limits. Two layers close this; use both.

## 1. LiteGate gives people the view-only role

LiteGate provisions people with LiteLLM's `internal_user_viewer` role. Viewers
use their keys for model requests and can see their own keys and spend, but
cannot create, update or delete keys. LiteGate keeps managing keys with the
master key.

- New people are created as viewers.
- An existing person with the plain `internal_user` role (or no role) is
  switched at their next sign-in, and once at startup for people LiteGate
  already knows (local accounts, SSO sign-ins and organization members).
- Each switch is audited as `litellm.user_role_restricted`.
- Administrators and any other role are never changed.

This needs no setting. People who never sign in through LiteGate keep their
LiteLLM role, which is why the second layer matters.

## 2. LiteLLM allows only administrators to create keys

Add this to LiteLLM's `config.yaml` (not LiteGate's) and restart LiteLLM:

```yaml
litellm_settings:
  key_generation_settings:
    personal_key_generation:
      allowed_user_roles: ["proxy_admin"]
    team_key_generation:
      allowed_team_member_roles: ["admin"]
```

LiteGate is unaffected: it creates keys with the master key, which has the
`proxy_admin` role. Team admins are a LiteLLM Enterprise feature; on other
installations no team member is an admin, so nobody else can create team keys.

## What was verified

Against the LiteLLM version pinned in
[`docker-compose.integration.yml`](../deploy/docker-compose/docker-compose.integration.yml)
(1.98.0), the [live integration tests](../backend/tests/integration/test_litellm_key_lockdown_live.py)
check that a person's own key cannot create a key or remove its budget,
while it still serves model requests and LiteGate still creates keys. Repeat
the check after upgrading LiteLLM:

```bash
curl -s -X POST "$LITELLM_URL/key/generate" -H "Authorization: Bearer <a person's key>" -d '{}'
```

The request must fail.

LiteLLM's `general_settings.ui_access_mode: admin_only` can also keep people
out of the Admin UI, but LiteLLM applies it only to SSO sign-in.
