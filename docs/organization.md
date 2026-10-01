# Organization hierarchy and budgets

LiteGate organizes users under configurable level labels and provides inherited
per-user allowances, top-level shared budgets, and administrative usage graphs.
LiteLLM remains the source of truth for budgets, spend, and request enforcement.
This integration targets current LiteLLM Enterprise with a database connected,
team-member budget updates including `budget_duration`, and `/user/daily/activity`.
LiteGate verifies the applied budgets rather than accepting ignored API fields.

## Configuration

Declare `organizationHierarchy` at the **top level** of Helm values. The default
`levels: []` disables the feature. A complete example:

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

Every root requires a distinct, stable `litellmTeamId`. LiteGate creates that
LiteLLM team when absent and manages its budget fields. Existing model and rate
policies are preserved. Lower groups are reporting groups, without separate
LiteLLM teams. Renaming a group requires updating its children's `parent` names;
keep the root's team ID stable to retain its upstream budget history.

Direct and Compose deployments accept the same `organizationHierarchy` block
in `config.yaml`, or its contents as JSON in `ORGANIZATION_HIERARCHY`. Helm
serializes the block into that variable and rolls out configuration changes.

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
Existing flat mappings remain supported, with the hierarchy's root taking
priority for managed key ownership. Other unmapped users retain existing behavior.

SSO users appear after successful login. Explicit IDs already present in LiteLLM
can synchronize before their next login. Stored claims come from the last verified
login; users sign in again after provider-side membership changes. This feature
does not add SCIM, LDAP, or identity-provider polling.

## Budgets

The closest explicitly configured `perUser` wins, overriding every ancestor's
per-user default. In the example Engineering defaults to $200, Digital overrides
that to $50, squad1 overrides it to $100, and squads 2–4 inherit $50.

`groupTotal` is a separate shared pool, supported only at the top level.
Engineering's $5,000 cap applies collectively, including squad1. Both limits must
allow a request. Individual allowances do not reserve part of the shared pool.
LiteLLM team-member budgets enforce allowances per internal user across key
replacement. Managed keys have no separate per-key budget.

Omitted `perUser` inherits. Explicit `perUser: null` disables that cap at this
group and below unless another descendant sets it. Root caps omitted or null
are unlimited. `0` is zero allowance, not unlimited; LiteLLM can still serve
explicitly free models. `duration` inherits independently and accepts values
such as `30d` (30-day duration) or `1mo` (calendar month), using LiteLLM's reset
behavior. A null duration means no automatic reset.

LiteGate reconciles roots and known users every 60 seconds with bounded
concurrency, and again during managed login/key creation.
Synchronization and key issuance serialize per user. A slow user's member update
does not hold a lock across other users; root-team policy writes serialize only
while that shared policy is being synchronized. Each queued operation rereads
the current verified membership before applying its policy.
Policy writes preserve accrued spend and leave unchanged reset durations out of
update requests. Changing
only an allowance retains its existing reset window; changing the duration uses
LiteLLM's reset scheduling. Lowering a cap below current spend may prevent further paid
requests immediately. Failures are shown in the admin dashboard.

Legacy `KEY_MAX_BUDGET` and `KEY_BUDGET_DURATION` do not apply to managed keys.
Existing unassigned keys adopt the root after the member budget is applied;
key caps are cleared and verified. Usage before joining that team is not
retroactively charged to its member budget. Keys belonging to another team,
and moves to another root, require explicit migration in LiteLLM. Review old
and new budget windows; LiteGate does not silently transfer/reset spend.

Managed budgets and membership are read-only in LiteGate. Managed roots cannot
be deleted or used for manual member moves. Bulk-key budget/team changes report
per-item failures. Model, rate-limit, and blocking controls remain available.
Reconciliation reasserts configured policies after drift in LiteLLM. Disabling
the feature leaves upstream teams, budgets, membership, and keys intact; review
them when retiring the configuration.

## Dashboard and reporting

Administrators open **Organization** to filter users and graphs by any level,
inspect effective allowances and current-cycle spend, and compare daily spend,
tokens, logged requests, groups, and models. Ordinary users and LiteLLM-key
identities cannot access administrative organization reports.

Parent groups start collapsed. Use the arrow beside a parent to show or hide its
children, and select a group name to filter the dashboard. Collapsing a parent
keeps the current filter; selecting a group through a chart expands its ancestors
in the navigation.

Charts use UTC daily aggregates, bounded concurrency, and a short process-local
cache. A report supports at most 90 days between dates and 500 users; select a
smaller group when necessary. Each user's analytics fetch follows up to 20
pages of 1,000 underlying daily records with a 60-second deadline, summing all
per-page daily and model aggregates. A page-limit error asks for a shorter date
range; a deadline returns `504`. Incomplete or unavailable upstream data produces
an error instead of partial totals. Dashboard loads do not scan raw spend logs.
Logged requests count upstream attempts, including retries, rather than all
gateway requests. Reporting totals are independent of budget resets.

Reports attribute the selected period to **current membership**. Moving a user
changes where their earlier usage appears; these graphs do not reconstruct
historical membership or replace LiteLLM's budget ledger.

Verified user IDs, emails, group values, and synchronization status use the
existing SQLite database. Identity-provider tokens are not stored. Keep the
existing single-replica deployment and persistent volume. The public demo uses
synthetic organizations and usage, without a backend or credentials.
