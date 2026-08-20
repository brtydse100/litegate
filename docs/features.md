# Features and access model

LiteGate provides a focused access layer in front of LiteLLM. LiteLLM continues
to own virtual keys, models, budgets, usage, and request routing; LiteGate adds a
human-friendly portal, identity integration, and a stable automation API.

## Self-service portal

Signed-in users can:

- create a LiteLLM virtual key with one click;
- reveal a newly created secret once and copy it;
- view masked identifiers, allowed models, expiration, spend, budget, TPM, and
  RPM;
- regenerate a personal key after confirmation, immediately invalidating the old
  key; and
- follow configured links to a support system or LiteLLM model hub.

New keys inherit the installation defaults for models, budget, reset interval,
duration, TPM, RPM, and team. For SSO users, an administrator can map identity
provider groups to existing LiteLLM teams so new or regenerated keys use the
matched team's model and budget policy. See
[SSO team mapping](authentication.md#mapping-sso-groups-to-litellm-teams) and
the [configuration guide](configuration.md#key-defaults).

## User and administrator roles

| Role | Capabilities |
| --- | --- |
| `user` | Sign in, create or regenerate a personal key, and view its access snapshot |
| `admin` | Everything a user can do, plus manage local users, LiteLLM teams, installation keys, and bulk key policy |

The administrator-only **Users** tab is useful for contractor access, SSO
outages or migrations, break-glass administration, and role testing. It supports
account creation, password resets, role changes, and enable/disable controls.
Disabling a local account invalidates its current portal session on the next
request.

## Administrator-only team management

The **Teams** tab lets administrators search and page through LiteLLM teams,
create a team, and edit its name, models, budget, reset interval, TPM/RPM limits,
or blocked state. The same operations are available to trusted automation through
the [v1 API](../API.md#teams-admin-only). Normal users cannot see the tab or call
the team endpoints.

Deletion is intentionally guarded because LiteLLM also deletes the team's
scoped API keys. LiteGate requires an administrator to type the exact team ID
before deleting it. Teams referenced by `oidc_group_team_mapping` or
`KEY_TEAM_ID` cannot be deleted until the administrator changes that
configuration.

## Administrator-only bulk editing

Only administrators can open the bulk editor or call
`PATCH /api/v1/keys/bulk`. This boundary applies even when a caller presents a
LiteLLM virtual key; that key can identify and inspect only itself.

The bulk editor lets an administrator:

- select individual keys or the current 25-key page;
- enter a key ID that is not visible on the current page;
- change aliases, models, budgets, reset intervals, TPM/RPM, duration, or blocked
  status; and
- submit only changed fields so untouched settings remain unchanged.

The API accepts up to 100 keys in a request, updates them with bounded
concurrency, and returns a result for each key so partial failures remain visible.
See the [API guide](../API.md#keys) for an example.

## Automation API

Stable routes live under `/api/v1`. Trusted automation agents should use the
optional `management_api_key` in the `X-API-Key` header. It is an
installation-wide administrator credential, not a separately scoped agent
account, so distribute it only to trusted systems and rotate it if exposed.

Automation supports:

- checking the current API identity;
- paginated administrator key listing;
- creating keys for a specified user;
- administrator-only bulk policy updates; and
- creating, listing, disabling, and updating local users; and
- creating, listing, updating, and safely deleting LiteLLM teams.

See [API v1](../API.md) for endpoint and authentication details.

## Performance behavior

The main dashboard does not download raw spend logs. It renders a compact access
snapshot from key records LiteLLM already returns. Installation-wide key lists
are fetched only when an administrator opens the bulk editor, and the list is
paginated to avoid loading every key at once.

## Deployment and customization

- The frontend and backend ship together in one Docker image behind Nginx.
- Docker Compose persists local accounts in a named volume.
- The included Helm chart supports a persistent volume claim.
- A health endpoint is available at `/api/health`.
- Administrators can configure a logo, LiteLLM model-hub link, and support link.

Continue with the [deployment guide](../DEPLOYMENT.md) or
[configuration reference](configuration.md).
