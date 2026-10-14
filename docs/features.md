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
- regenerate a personal key after confirmation while carrying its accumulated
  spend into the replacement and invalidating the old key; and
- follow configured links to a support system or LiteLLM model hub.

Deployments can opt into [API key storage](configuration.md#optional-api-key-storage).
For saved keys, **Show API key** replaces regeneration in the portal; owners can
reveal their own keys and administrators can reveal them from the key list.
The default remains one-time secret display without key storage.

New keys inherit the installation defaults for models, budget, reset interval,
duration, TPM, RPM, and team. For SSO users, an administrator can map identity
provider groups to existing LiteLLM teams so new or regenerated keys use the
matched team's model and budget policy. See
[SSO team mapping](authentication.md#mapping-sso-groups-to-litellm-teams) and
the [configuration guide](configuration.md#key-defaults).

The portal disables key, local-account, team, and bulk-edit controls when the
server-side mutation limit is exhausted and shows the live cooldown. This
prevents repeated clicks while retaining the backend rate limit as the
authoritative protection.

## User and administrator roles

| Role | Capabilities |
| --- | --- |
| `user` | Sign in, create or regenerate a personal key, and view its access snapshot, including the accessible model list |
| `admin` | Everything a user can do, plus manage local users, LiteLLM teams, installation keys, and bulk key policy |

The administrator-only **Users** tab is useful for contractor access, SSO
outages or migrations, break-glass administration, and role testing. It supports
account creation, password resets, role changes, and enable/disable controls.
Disabling a local account invalidates its current portal session on the next
request.

## Administrator-only team management

The **Teams** tab lets administrators search and page through LiteLLM teams,
create a team, and edit its name, models, budget, reset interval, TPM/RPM limits,
or blocked state. Its **Members** action also lets an administrator move a user
to another team in a few clicks. The same operations are available to trusted
automation through the [v1 API](../API.md#teams-admin-only). Normal users cannot
see the tab or call the team endpoints.

The team editor keeps a **Current team settings** summary visible while you
edit. It prefills saved values and offers model checkboxes and common
budget-reset durations. Saved models remain selectable even if they are missing
from the current catalog. Custom durations remain supported.
Numeric budget and rate-limit fields use styled minus/plus buttons alongside
direct numeric input. Model selections stay readable in light and dark themes.
Checkboxes follow the selected theme, with muted backgrounds, indigo checks,
and visible keyboard focus. System high-contrast mode uses native checkboxes.

A move deliberately changes the policy applied to that user's source-team keys.
LiteGate first adds the destination membership, reassigns and verifies every
source-team key, and only then removes the source membership. The administrator
must acknowledge the model, limit, and budget change. If key migration fails,
the source membership is retained. Moves out of a team referenced by
`oidc_group_team_mapping` or `KEY_TEAM_ID` are blocked because configuration
would otherwise restore or conflict with the membership.

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

- search globally by owner, alias, team, or key ID and filter by team or blocked state;
- select individual keys, the current page, every key, or every matching result;
- change aliases, models, budgets, reset intervals, TPM/RPM, duration, or blocked
  status;
- reset selected keys' accumulated spend to zero after confirmation while
  preserving their budgets, limits, and LiteLLM spend logs; and
- submit only changed fields so untouched settings remain unchanged.

After selecting keys, **Current key settings** shows each selected key's saved
budget, reset interval, models, rate limits, status and available expiry metadata
on the current page. Selections on other pages are explicitly identified;
their settings are not assumed to match. Inspecting a key does not submit its
saved settings or overwrite unrelated values.
**Choose settings to change** starts collapsed and opens when keys are selected.
It can be collapsed manually; changing the selection opens it again. Model
choices appear in a scrollable list with highlighted selections and a count.
The editable fields themselves are prefilled with the selected key's saved
values. Key and team fields also use saved values as placeholders, so clearing
an edit still shows the current setting. When all selected keys are visible, shared values are filled in and
different values are marked **Mixed values**. When the selection includes keys
on another page, fields show **Current values unavailable** rather than assuming
that the visible keys represent the entire selection. Only edited, filled
fields are submitted; changing the selected keys resets field edits.
Models are selected using checkboxes, with saved models already checked. Model
names remain array entries through submission, without comma-separated input.
Select **All allowed models** explicitly to remove model restrictions; an empty
selection alone cannot grant unrestricted access. Common reset/lifetime durations
are available alongside custom duration input.

Select **Use key budget as the individual allowance** to remove a duplicate
personal user cap and the owner's team-member cap for the key's team. This
requires one key per owner and a finite key budget; shared team budgets still
apply. You can migrate an existing key with its saved budget, or enter a new
key budget at the same time. LiteGate verifies the change and keeps failures
selected for retry. This is an explicit administrator action, not a change
performed during ordinary user login or key creation.

The API accepts up to 5,000 keys in a request, updates them with bounded
concurrency, and returns a result for each key so partial failures remain visible,
selected, retryable, and downloadable as a failure report.
The select-all action is explicit: normal dashboard loads remain lightweight,
and the browser receives the full identifier list only when an administrator
requests it.
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
- administrator-only bulk policy updates and selected-key spend resets;
- creating, listing, disabling, and updating local users; and
- creating, listing, updating, safely deleting LiteLLM teams, and moving their members and scoped keys.

See [API v1](../API.md) for endpoint and authentication details.

## Performance behavior

The main dashboard does not download raw spend logs. It renders a compact access
snapshot from key records LiteLLM already returns. Installation-wide key lists
are fetched only when an administrator opens the bulk editor, and the list is
paginated to avoid loading every key at once.

## Deployment and customization

- The frontend and backend ship together in one non-root Docker image behind Nginx.
- Docker Compose persists local accounts in a named volume.
- The included Helm chart supports a persistent volume claim.
- Separate liveness and dependency-aware readiness endpoints are available at
  `/api/health/live` and `/api/health/ready`.
- Every response carries an `X-Request-ID`; secret-free structured request logs
  use the same ID, and authenticated Prometheus metrics are available at
  `/api/v1/metrics`.
- The included maintenance command creates consistent SQLite backups, verifies
  integrity, and preserves a safety copy before an explicitly confirmed restore.
- The administrator **Status** tab shows LiteLLM/database readiness, actionable
  deployment-security warnings, and a
  secret-safe audit history of management changes.
- Administrators can configure a logo, LiteLLM model-hub link, and support link.

Continue with the [deployment guide](../DEPLOYMENT.md) or
[configuration reference](configuration.md).
