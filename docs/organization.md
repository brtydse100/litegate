# Organization hierarchy and budgets

## Progressive organization navigation

The Organization page initially loads only root-group metadata from LiteGate's
configured hierarchy and local identity records. It does not wait for live
LiteLLM data for every internal team, and it does not request installation-wide
usage or users before a selection.

Select or expand a group to fetch its direct children and that team's current
details. Deeper groups load the same way as you open them. Child lists, team
details, users and usage have separate loading/error states and retry controls;
navigation remains usable while a slow branch or chart request completes.
Fetched branches and selected data are cached for 60 seconds for quick revisits.

The current team's spend is labelled as **team spend**, not a descendant total.
Usage charts aggregate the explicitly selected subtree over the selected date
range. **All groups** is an explicit request for organization-wide reporting,
which can be more expensive. Existing hierarchy policy and membership protections
still apply. The legacy full-overview API remains available for existing clients;
the page uses the lightweight children/detail endpoints described in [API.md](../API.md).

LiteGate organizes users under configurable level labels and provides inherited
per-key allowances, aggregate budget tracking, and administrative usage graphs.
LiteLLM remains the source of truth for budgets, spend, and request enforcement.
This integration requires LiteLLM with a database and its key/team management APIs.
Detailed daily graphs also require `/user/daily/activity`; its availability depends
on the deployed LiteLLM version and license. Parent budget tracking does not add
request enforcement or require a nested-team enforcement feature.
LiteGate verifies the applied budgets rather than accepting ignored API fields.

## Configuration

The hierarchy is available in Docker/Compose, direct backend deployments, and
Helm with the same schema and policies. Declare `organizationHierarchy` at the
**top level** of `config.yaml` for Docker/direct deployments, or at the **top
level** of Helm values (outside `config`). The default `levels: []` disables
the feature. You can configure up to eight levels. A complete inline example:

```yaml
organizationHierarchy:
  levels:
    - name: "Division"
      groups:
        - members:
            - name: Engineering
              litellmTeamId: engineering
              ssoGroups: ["engineering-users"]
              budget: { duration: "30d", groupTotal: 5000, perUser: 200 }
            - name: Marketing
              litellmTeamId: marketing
              budget: { duration: "30d", groupTotal: 2000, perUser: 50 }

    - name: "Business Unit"
      groups:
        - parent: Engineering
          members:
            - { name: Digital, ssoGroups: ["digital-users"], budget: { perUser: 50 } }
        - parent: Marketing
          members:
            - { name: Campaigns, ssoGroups: ["campaign-users"] }

    - name: "Squad"
      groups:
        - parent: Digital
          members:
            - { name: squad1, ssoGroups: ["squad1-users", "external-squad1"], budget: { perUser: 100 } }
            - { name: squad2, ssoGroups: ["squad2-users"] }
            - { name: squad3, userIds: ["local:alice"] }
            - { name: squad4, ssoGroups: ["squad4-users"] }
        - parent: Campaigns
          members:
            - { name: Social, ssoGroups: ["social-users"] }
```

`members` lists **groups within that level**, rather than people. Each bundle
declares its `parent` once, referencing the immediately preceding level. Root
bundles omit `parent`. Level order comes from the list. Group names must be
unique within each level. All labels and names are deployment-defined. Invalid
parents, conflicting mappings, duplicate names, and invalid budgets are rejected.

Every group has its own distinct LiteLLM team. Roots require `litellmTeamId`;
children may set one explicitly or use a deterministic `litegate-org-<path hash>`
ID. LiteGate creates missing teams and preserves existing models and rate limits.
Use explicit child IDs when group names may change: renaming a path changes an
automatically generated ID and requires reviewing existing key assignments.
Renaming a group also requires updating its children's `parent` names.

### Docker and Compose

Add the block above to `deploy/docker-compose/config.yaml`, alongside settings
such as `litellm_url`. Both supplied Compose files mount that host file read-only
at `/app/backend/config.yaml`; no extra mount is needed for inline YAML. The
[smaller YAML example](examples/organization-hierarchy.yaml) is also ready to
merge into that file.

Alternatively, add an `environment` block to the existing `litegate` service in
your Compose file. `ORGANIZATION_HIERARCHY` takes a JSON object with `levels` at
its root, without the `organizationHierarchy` wrapper:

```yaml
services:
  litegate:
    environment:
      ORGANIZATION_HIERARCHY: >-
        {"levels":[
          {"name":"Division","groups":[{"members":[
            {"name":"Engineering","litellmTeamId":"engineering",
             "ssoGroups":["engineers"],"budget":{"perUser":100,"duration":"30d"}}
          ]}]},
          {"name":"Team","groups":[{"parent":"Engineering","members":[
            {"name":"Platform","userIds":["alice@example.com","local:operator"],
             "budget":{"perUser":50}}
          ]}]}
        ]}
```

This is the same hierarchy as the complete [JSON example](examples/organization-hierarchy.json).
For plain Docker, pass the same JSON with `-e 'ORGANIZATION_HIERARCHY=<JSON>'`.
Environment variables override YAML settings; choose one inline source to avoid
stale overrides. Leave `organization_hierarchy_file` / `ORGANIZATION_HIERARCHY_FILE`
empty when using inline levels. A nonempty file path and nonempty inline levels,
even from different sources, fail startup rather than selecting one.

Settings and hierarchy files load at startup. From `deploy/docker-compose`, apply
changes to the release-image deployment with:

```bash
docker compose -f docker-compose.image.yml up -d --force-recreate
```

Use `docker compose up -d --force-recreate` for the local-build Compose file
after building its image. Recreating applies changed service environment and
mounts as well as changed file contents. Reconciliation updates configured team
and key policy periodically; it does not reload configuration from disk.

For a direct backend deployment, LiteGate reads `backend/config.yaml`, falling
back to the repository-root `config.yaml` only when the first file is absent.
Restart the backend after changes. Helm serializes top-level
`organizationHierarchy` into `ORGANIZATION_HIERARCHY` and rolls out inline changes.

## JSON file input

Instead of inline configuration, save the [JSON hierarchy value](examples/organization-hierarchy.json)
as `organization.json`. Its root is `{"levels": [...]}` without an
`organizationHierarchy` wrapper. `userIds`, `ssoGroups`, parent links, and budgets
use exactly the same validation and resolution as inline hierarchy configuration.
The [YAML sample](examples/organization-hierarchy.yaml) includes the inline wrapper;
do not save that wrapper in the JSON file.

For direct deployment, set `organization_hierarchy_file: organization.json` in
`config.yaml`, or `ORGANIZATION_HIERARCHY_FILE=organization.json`. Relative paths
resolve against `backend/`. Leave inline levels empty or omit the inline setting.
Nonempty inline levels plus a nonempty file path fail startup. Environment values
retain precedence over YAML. The file must be readable UTF-8 JSON and is validated
at startup; missing, unreadable, malformed, and invalid files stop startup with an
actionable error. There is no file watcher; restart after editing.

For Docker Compose, save `organization.json` beside `deploy/docker-compose/config.yaml`
and set this in that config file:

```yaml
organization_hierarchy_file: /app/backend/organization.json
```

Add the read-only file mount to the existing `litegate` service in the Compose
file you run, keeping the config and SQLite mounts:

```yaml
services:
  litegate:
    volumes:
      - ./config.yaml:/app/backend/config.yaml:ro
      - litegate-data:/app/backend/data
      - ./organization.json:/app/backend/organization.json:ro
```

The host file must exist and be readable by the container's UID/GID `10001`.
The setting uses the destination **inside the container**, not the host path;
relative file settings resolve against `/app/backend` there. Recreate the service
with the command above after adding a mount or changing the file. For plain
Docker, use `--mount type=bind,src=<absolute-host-path>,dst=/app/backend/organization.json,readonly`
and `-e ORGANIZATION_HIERARCHY_FILE=/app/backend/organization.json`.

For Helm, create a ConfigMap in the release namespace:

```bash
kubectl create configmap litegate-hierarchy --from-file=organization.json=docs/examples/organization-hierarchy.json
```

Then set this **top-level** values block:

```yaml
organizationHierarchyFile:
  configMap: litegate-hierarchy
  key: organization.json
  mountPath: /etc/litegate/organization.json
```

The default is `organizationHierarchyFile: {}` (off). With a ConfigMap selected,
`key` defaults to `organization.json` and `mountPath` to
`/etc/litegate/organization.json`. The destination must be an absolute file path.
The chart mounts the selected key read-only using `subPath` and sets
`ORGANIZATION_HIERARCHY_FILE` automatically. Nonempty inline hierarchy levels
cannot be combined with the file. A key or path without a nonempty `configMap`
is rejected. No Secret or additional enable toggle is required.

Inline configuration keeps its existing rollout checksum. File option changes
also trigger rollout, but edits to the external ConfigMap's contents do not.
Because `subPath` mounts and startup loading do not refresh automatically, restart
the deployment after updating the ConfigMap:

```bash
kubectl rollout restart deployment/<release-name>-litegate
```

Use your deployment's actual name (a name override may change it). This file input
adds no new authentication, email-verification, identity-binding, or budget policy.
The removed `organization_mapping_file` setting and its standalone schema remain
unsupported.

## Membership

`ssoGroups` matches any listed group name or ID from the verified login provider,
case-insensitively. The existing `oidcGroupsClaim` setting supports dotted claim
paths and applies to OIDC and generic OAuth. `userIds` matches exact internal IDs,
including local accounts such as `local:alice`; the Local users page shows IDs.

A match assigns the group and all its ancestors. Multiple matches must lie on
one path; the deepest compatible match wins. A higher-level match does not guess
a child. Conflicting paths reject login before a session is issued. A removed
mapping for a previously managed user blocks new login and key creation/replacement until
an administrator resolves it. A hierarchy match satisfies `ssoRequireTeamMapping`.
Verified removed or conflicting claims are saved before rejecting login, so
existing sessions also lose permission to create or replace a managed key.
Existing flat mappings remain supported, with the hierarchy's deepest match taking
priority for managed key ownership. Flat mappings and the default SSO team cannot
automatically add memberships in other managed teams; those memberships come from the
resolved hierarchy path. Mappings to other, unmanaged teams remain supported.

SSO users appear after successful login. Explicit IDs already present in LiteLLM
can synchronize before their next login. Stored claims come from the last verified
login; users sign in again after provider-side membership changes. This feature
does not add SCIM, LDAP, or identity-provider polling.

## Budgets

The closest explicitly configured `perUser` wins, overriding every ancestor's
per-user default. In the example Engineering defaults to $200, Digital overrides
that to $50, squad1 overrides it to $100, and squads 2–4 inherit $50.

The inherited `perUser` value is the allowance on each user's unique key; the
configuration name is retained for compatibility. The key belongs to the deepest
matched group, including users assigned directly to a middle level. Duplicate
personal-user and team-member caps are removed only after the key policy is
applied and verified. Normal creation remains limited to one key per user,
including concurrent creation requests.

`groupTotal` is an informational tracking target, allowed at any level.
Engineering's $5,000 target compares against direct-team and descendant-team
usage, counting each distinct team once. Exceeding it does **not** block keys.
Managed teams have no native shared spend cap; individual keys enforce the
inherited allowance. Native shared budgets on unrelated, unmanaged teams remain
unchanged. Detailed historical user graphs attribute usage to current membership.

Omitted `perUser` inherits. Explicit `perUser: null` disables that cap at this
group and below unless another descendant sets it. Tracking targets omitted or
null have no threshold. `0` is zero key allowance, not unlimited; LiteLLM can still serve
explicitly free models. `duration` inherits independently and accepts values
such as `30d` (30-day duration) or `1mo` (calendar month), using LiteLLM's reset
behavior. A null duration means no automatic reset.

LiteGate clears and verifies personal/member caps and default member caps on
managed teams. Before removing an old native shared cap, every affected key must
match its owner's configured allowance and assignment. Unknown or unmigrated
credentials keep that old cap in place and produce a synchronization warning.
Spend, model access, roles and rate limits are preserved. Missing verification
records block normalization rather than being interpreted as an unlimited budget.

LiteGate reconciles all group teams and known users every 60 seconds with bounded
concurrency, and again during managed login/key creation.
An explicit-user discovery failure is logged independently and does not prevent
that cycle from updating teams and known users.
Synchronization and key issuance serialize per user. A slow user's key update
does not hold a lock across other users; team policy writes serialize only
while that shared policy is being synchronized. Each queued operation rereads
the current verified membership before applying its policy.
Policy writes preserve accrued spend and leave unchanged reset durations out of
update requests. Changing
only an allowance retains its existing reset window; changing the duration uses
LiteLLM's reset scheduling. Lowering a cap below current spend may prevent further paid
requests immediately. Failures are shown in the admin dashboard.

**Rate limits:** Hierarchy budgets are USD spending allowances, not request or token rate limits.
`perUser` sets each managed key's spend allowance; `groupTotal` only tracks
aggregate spend. Neither field sets requests per minute (RPM), tokens per minute
(TPM), or concurrent request limits, and the hierarchy has no inherited rate-limit
fields. For newly generated keys, use root-level `key_rpm_limit`, `key_tpm_limit`,
and `key_max_parallel_requests` in `config.yaml` (or their uppercase environment
variables). Configure team and existing-key rate limits in LiteLLM. These controls
are independent of budget duration and are not aggregate hierarchy limits.

Legacy `KEY_MAX_BUDGET` and `KEY_BUDGET_DURATION` do not apply to managed keys.
All existing owned keys, including keys assigned to an unmanaged team or another
hierarchy path, adopt the deepest configured team with the inherited key
allowance during login and reconciliation. Migration supports at most 500 keys
per user and preserves existing secrets and spend. Review old and new budget
windows; LiteGate does not reset spend. Rotation carries accrued key spend into the replacement, whose
reset schedule is established by LiteLLM for that new key.
Rotation verifies live owned-key counters after replacement policy updates and
before deleting originals. If LiteLLM cannot confirm carried spend, LiteGate
rejects the rotation and revokes the replacement, retaining the original key.
Ancestor model, blocking, permission, and rate policies are not inherited by native
child teams. LiteGate blocks provisioning or migration when it detects these
restrictions on an ancestor (including member rate limits on a key's source team).
An operator must review and explicitly configure the intended controls in LiteLLM
before removing the ancestor restrictions and retrying synchronization.
When a user's configured root changes, LiteGate adds the destination memberships
and moves their keys without removing old memberships or resetting their spend
records. Administrators can review and remove stale memberships separately.

Managed budgets and membership are read-only in LiteGate. Managed teams cannot
be deleted or used for manual member moves. Bulk-key budget/team changes report
per-item failures. Model, rate-limit, and blocking controls remain available.
Reconciliation reasserts configured policies after drift in LiteLLM. Disabling
the feature leaves upstream teams, budgets, membership, and keys intact; review
them when retiring the configuration.

LiteGate records a user's assigned team before changing their managed keys.
An unsuccessful response or verification keeps that team binding and reports a
synchronization error. Retrying synchronization resumes the move; a subsequent
configuration change uses the current mapping without resetting key spend.

The personal dashboard shows the allowance LiteLLM currently enforces, with a
warning for policy drift or removed mappings. Budget lookup outages leave key
metadata and the regeneration action visible, with budget/spend marked
Unavailable. A failed key listing does not offer key creation. Cancellation
during managed key verification or rotation cleanup revokes the undelivered
replacement before the operation finishes.

## Dashboard and reporting

Administrators open **Organization** to filter users and graphs by any level,
inspect effective allowances and current-cycle spend, and compare daily spend,
tokens, logged requests, groups, and models. Ordinary users and LiteLLM-key
identities cannot access administrative organization reports.

Groups without child groups show **Usage by member**, with each person's email
or user ID and spending for the selected dates. The metric selector also shows
individual tokens and logged requests. These totals include all selected members,
including those with zero usage, and reconcile with the report total. Higher
levels retain the child-group breakdown. The user table separately displays
**Budget-period spend / per-key allowance**, which is independent of the chart's
date filter and can differ after budget resets.
Spend chart labels adjust their precision for small amounts, and usage bars
scale to the largest value in the selected results. The personal dashboard reads
live key counters; historical chart totals do not overwrite current budget
counters or reconstruct counters that have already been reset.
If an older report omits the member breakdown, the chart retains group totals
with an explicit unavailable message rather than treating members as zero usage.

Parent groups start collapsed. Use the arrow beside a parent to show or hide its
children, and select a group name to filter the dashboard. Collapsing a parent
keeps the current filter; selecting a group through a chart expands its ancestors
in the navigation. If a selected group is removed or renamed during a hierarchy
refresh, the filter and pagination reset to All groups.

Charts use UTC daily aggregates, bounded concurrency, and a short process-local
cache. A report supports at most 90 days between dates and 500 users; select a
smaller group when necessary. Each user's analytics fetch follows up to 20
pages of 1,000 underlying daily records with a 60-second deadline, summing all
per-page daily and model aggregates. A page-limit error asks for a shorter date
range; a deadline returns `504`. Incomplete or unavailable upstream data produces
an error instead of partial totals. Required metrics, finite non-negative values,
integer counts, dates, and model breakdowns are validated before a fetch enters
the cache. A corrected retry can therefore recover immediately from malformed
data. Dashboard loads do not scan raw spend logs.
Logged requests count upstream attempts, including retries, rather than all
gateway requests. Reporting totals are independent of budget resets.

Failed or cancelled reports cancel and await outstanding user analytics fetches.
Group breakdowns use group IDs for aggregation and chart drill-down. `Direct members`
is the display label for direct assignments, with a null ID; a child group with
that same name remains a separate, selectable bucket with its own ID.

Reports attribute the selected period to **current membership**. Moving a user
changes where their earlier usage appears; these graphs do not reconstruct
historical membership or replace LiteLLM's budget ledger.

Verified user IDs, emails, group values, and synchronization status use the
existing SQLite database. Identity-provider tokens are not stored. Keep the
existing single-replica deployment and persistent volume. The public demo uses
synthetic organizations and usage, without a backend or credentials. Its shared
30-day UTC dataset reconciles member, group, daily and model reporting totals
with the displayed demo budget-period spend. Shorter date ranges use that same
dataset; dates before the demo period have zero usage.

## Individual SSO email assignments

Use the existing `organizationHierarchy` (`organization_hierarchy` or
`ORGANIZATION_HIERARCHY` for backend configuration). Each member's `userIds`
accepts exact existing user IDs and SSO email addresses. Email matching trims
whitespace and ignores case; existing ID matching remains exact. Authenticated SSO claims can match by email. Startup can also discover an
existing remote account as an operator assignment; local accounts require exact IDs.

Email and `ssoGroups` matches use the same single-path resolver. Compatible
ancestor matches select the deepest team and its inherited budget. Conflicting
paths reject access rather than selecting one by order. Ancestor membership,
key migration, and enforced allowances use the existing hierarchy lifecycle.

Startup awaits the first hierarchy reconciliation attempt before serving requests,
then retries every 60 seconds. Exact existing user IDs take precedence, including
IDs containing `@`. Unresolved email selectors search all matching LiteLLM pages
(case-insensitive substring search), then require one normalized exact match and
a fresh lookup by actual user ID. Discovery uses at most five concurrent lookups,
100 pages of 100 users per email, a 60-second scan deadline, and existing request
timeouts. Missing users are skipped and retried; no users, keys, SSO bindings or
reservations are created by this pass.

Email discovery is an operator-configured organization assignment
(`configured_email`), not SSO identity proof. Local/admin email-only matches,
ambiguous or incomplete results, changed emails and incompatible paths are
skipped with actionable errors. Remote-derived assignments are revalidated before
every reconciliation pass; failed validation blocks policy writes and never
silently reuses the previous team. Verified SSO/local claims, including rejected
claims, remain authoritative. Subject-based login, email verification and existing
bindings are unchanged; new SSO users are provisioned keylessly only at login.

Existing keys keep their secrets, aliases, model access and spend during policy
migration. Per-user errors remain visible; finishing the startup attempt does
not guarantee every remote write succeeded. Review synchronization errors and
retry after correcting upstream availability or conflicting assignments.
The Helm startup probe allows 30 minutes before liveness checks begin; installations
with larger migrations must allow more startup time. No new backend setting is
required.

In 2.15.1, `organization_mapping`, `organization_mapping_file`,
`config.organizationMapping`, and `config.organizationMappingFile` are removed.
Remove those options and optional JSON mounts. Move old `members` emails into
`userIds` of the corresponding hierarchy member; move `team_id` to
`litellmTeamId`, and express parent links through the existing `groups` bundles.
The old flat/object-based groups schema is not accepted. Nonempty removed
options fail with a migration message. Preserve the SQLite volume: existing
2.15.0 provider/subject bindings keep their canonical users, keys, spend, and
memberships. Unbound reservations require durable remote ownership evidence;
unproven pending candidates require their authenticated existing subject.
No users are deleted and no key ownership is transferred.

See [YAML example](examples/organization-hierarchy.yaml) and
[JSON hierarchy value](examples/organization-hierarchy.json). JSON is the value
of `ORGANIZATION_HIERARCHY`, not a separately mounted mapping file.
