# Organization access, personal analytics, and budget planning

These LiteGate capabilities work without a LiteLLM Enterprise license. An
Enterprise deployment may additionally provide native team-admin roles and other
upstream features. LiteGate never disables upstream license or policy validation.

## Scoped Organization access

System administrators retain existing access. A delegated person needs both:

1. A designation for a configured hierarchy team.
2. Administration of that team, through LiteGate configuration or a live native
   LiteLLM team-admin role.

Use canonical user IDs from the administrator **People** directory, not email
addresses or display names. LiteGate-managed administration grants only scoped
Organization capabilities, not global administration or native LiteLLM roles.
Authority applies to the designated root and descendants. Multiple roots are
supported. Backend checks run on every request. Native team-admin roles are
cached for 30 seconds, so a removed native role stops granting access within
30 seconds. If LiteLLM is briefly unreachable, the last successful answer is used
for up to 5 minutes; with no recent answer, a lookup failure grants nothing.
Configuration changes require the usual application restart/rollout.

Docker/direct `config.yaml`:

```yaml
organization_access_designations:
  oidc-subject-alice: [engineering]
organization_group_admins:
  engineering: [oidc-subject-alice]
```

Helm values:

```yaml
config:
  organizationAccessDesignations:
    oidc-subject-alice: [engineering]
  organizationGroupAdmins:
    engineering: [oidc-subject-alice]
```

The IDs such as `engineering` must be existing team IDs in the configured
hierarchy. Designation alone, group administration alone, ordinary membership,
and possession of an API key do not qualify. Other administrative APIs remain
system-admin only. Parent names, other users, issues, usage, and totals outside
the authorized subtree are excluded from responses.

The People directory is read-only and available to system administrators even
when local password accounts are disabled. Search uses the upstream email
substring contract. Local password-account APIs and actions retain their existing
contracts; SSO/no-key accounts do not become local password accounts.

## Personal analytics

Every portal user can open **Analytics**, independently of group administration.
The service scans a bounded, paginated user roster once per aggregation pass,
then fetches complete daily usage aggregates with bounded concurrency. It never
uses the truncated raw-log summary as its data source.

An initial background refresh starts after application startup. Later passes
start hourly, allowing for the previous pass's work duration and never
overlapping. A pass taking longer than an hour delays the next pass rather than
starting competing collectors. The roster scan is limited to 100 pages of 100
users and 120 seconds; individual usage scans keep their existing pagination and
60-second limits. Previously known users are still refreshed after discovery
failure. Large installations should monitor refresh age and upstream latency.

The first refresh for a user reads the full retention window. Later passes read
only from the last stored day through today and merge those days into the
snapshot; days older than the retention window are dropped. Roster discovery
adds users without overwriting the email or sign-in source recorded at portal
sign-in. After a complete roster scan, users LiteLLM no longer lists and who have
not signed in for 24 hours are removed with their cached snapshots. Portal
sign-ins record the user at most once an hour unless their email or sign-in
source changes.

Indexed SQLite snapshots contain request/token/cost totals, daily/model data,
coverage, and last successful refresh time. Each complete user snapshot commits
atomically. Failure retains the previous snapshot; a first failure is displayed
as unavailable. Missing input/output metrics are unavailable, not fabricated zero
values. The UI defaults to the latest 30 days within retained coverage. Snapshot
budget values have the same refresh age; separate key/reset allowances stay
separate. These are historical reports, not request-time budget enforcement.

Dashboard reads query only local snapshots and always select the authenticated
owner. They cannot select another user, even through an added query parameter.
Raw logs, key secrets/hashes, and upstream API-key breakdowns are not returned.

## Configuration parity

| Backend YAML | Environment | Helm `config` | Default |
| --- | --- | --- | --- |
| `organization_access_designations` | `ORGANIZATION_ACCESS_DESIGNATIONS` | `organizationAccessDesignations` | `{}` |
| `organization_group_admins` | `ORGANIZATION_GROUP_ADMINS` | `organizationGroupAdmins` | `{}` |
| `organization_cleanup_enabled` | `ORGANIZATION_CLEANUP_ENABLED` | `organizationCleanupEnabled` | `false` |
| `analytics_enabled` | `ANALYTICS_ENABLED` | `analyticsEnabled` | `true` |
| `analytics_retention_days` | `ANALYTICS_RETENTION_DAYS` | `analyticsRetentionDays` | `90` |
| `analytics_batch_concurrency` | `ANALYTICS_BATCH_CONCURRENCY` | `analyticsBatchConcurrency` | `5` |
| `hierarchical_budgets_enabled` | `HIERARCHICAL_BUDGETS_ENABLED` | `hierarchicalBudgetsEnabled` | `false` |
| `hierarchical_budgets_enforced` | `HIERARCHICAL_BUDGETS_ENFORCED` | `hierarchicalBudgetsEnforced` | `false` |
| `key_rotation_settle_seconds` | `KEY_ROTATION_SETTLE_SECONDS` | `keyRotationSettleSeconds` | `12` |

Environment mappings use JSON objects. Retention accepts 1–366 days; concurrency
accepts 1–20. Helm validates these types and rolls the pod when ConfigMap-backed
configuration changes. Docker/Compose reads the equivalent settings from its
mounted YAML or environment, followed by container recreation.

## Persistent storage, including SSO-only installations

The SQLite database contains saved key copies, SSO bindings, audit history,
analytics snapshots, and budget proposals. `local_users_db_path` names this shared
database; it is needed even when local password accounts are disabled.

Helm:

```yaml
persistence:
  enabled: true
config:
  localUsersDbPath: /app/backend/data/litegate.db
  saveApiKeysInDb: true
```

Both supplied Docker Compose deployments already mount `litegate-data` at
`/app/backend/data`. Keep the same Compose project/volume and database path during
upgrades. Do not remove volumes during an upgrade. Plain `docker run` also needs
a persistent volume mounted at that path. Set `save_api_keys_in_db: true` when
saved key reveal is needed; the database is used for other state even when this
setting is false. Use SQLite-aware backup before moving an existing live database
into a new PVC; enabling a PVC alone does not transfer the old pod's data.

An ephemeral database loses saved copies when its pod/container is replaced.
That does not revoke upstream credentials. Missing stored copies are not key
hashes that can be reversed. Preserve the database and owner instead of rotating
an otherwise valid key. Protect database backups because stored copies are usable
plaintext credentials.

## Budget planning and current enforcement boundary

Currency displays use exactly two decimal places for readability. Sub-cent
charges round to `$0.00` on screen; stored usage, allocation calculations and
numeric editing retain their full precision.

The opt-in budget page stores allocations. Without enforcement they are
**proposals**; with `hierarchical_budgets_enforced` they cap members' keys (see
[Enforced equal splits](#enforced-equal-splits)). Child envelopes and manual direct-user overrides reserve
funds first; the remainder is divided equally among other direct users using
integer micro-dollars. Children allocate recursively; descendant users are not
counted twice. Zero is a manual zero allocation; a blank override means automatic.
Manual overrides persist across recalculation. Conflicting revision edits and
over-allocation are rejected transactionally. Delegates cannot edit their scoped
root envelope or raise their own personal allowance, including indirectly.
Team administrators redistribute the team's existing allowance among members
and child teams; redistribution cannot expand that team's assigned total.
Only an authorized parent or system administrator changes the assigned total.
The backend enforces this restriction even for direct API requests.

Invalid legacy proposals remain visible with a group-specific allocation error.
Automatic shares and allocation totals are unavailable until repaired; explicit
overrides remain visible. System administrators and delegates may repair
deficits incrementally, provided no group's deficit increases. An existing
deficit in another group, including one outside a delegate's scope, does not
block unrelated edits.

Existing per-key enforcement remains active. The page reports unknown used and
remaining amounts as unavailable. Without enforcement it marks proposals as not
applied, and its Activate action returns 503. A native adapter and durable apply journal are covered by contract
tests, including aggregate member caps and verified decreases before increases.
They are not called from proposal editing.

## Enforced equal splits

Set `hierarchical_budgets_enforced: true` (environment
`HIERARCHICAL_BUDGETS_ENFORCED`, Helm `config.hierarchicalBudgetsEnforced`) to
turn group budgets into key caps. It is off by default because it can lower
existing caps. It works without the Budget planning page, which only adds manual
values on top.

- A group is **budgeted** when it has `groupTotal`, a planning-page envelope, or
  a manual override for one of its members. Its amount, minus budgeted child
  groups and manual overrides, is shared **equally** by its participating direct
  members. No administrator action is needed.
- **Participants** are members who signed in or already hold a key. Nobody is
  reserved a share before they use LiteGate. When someone signs in for the first
  time, every share in their group is recalculated; the 60-second
  reconciliation applies the new caps. Upgrading counts users who already signed
  in.
- `perUser` remains a **ceiling** on each share. Members of unbudgeted groups
  keep their fixed `perUser` allowance, and those groups are not deducted from
  their parent.
- Shares never fall below a member's current-period spend, so a newcomer only
  shares what is left. Shares are recalculated every pass from current spend,
  so a restart or a period reset is reflected, but a key is only rewritten when
  its share actually changes. Every enforced write collects current managed-key
  spend before pinning shares. Reconciliation reuses that roster while applying
  policy. Required decreases are verified before any increases; a failed read or
  decrease aborts the operation without raising caps.
- Enforced accounts support **one key**. Multiple-key owners stop the operation
  before existing controls are removed. Additional key creation is rejected.
- Members replace their own key with **Regenerate key**. LiteGate first blocks the
  old key, waits `KEY_ROTATION_SETTLE_SECONDS` (12 by default; keep it above
  LiteLLM's `proxy_batch_write_at`) for batched spend writes, then creates
  the replacement starting from that spend and deletes the old key. If any step
  fails, the old key is unblocked and kept. A key left blocked by an interrupted
  replacement (for example a restart) is unblocked at the member's next sign-in
  or synchronization. After a restart that lost the database, the member must
  sign in again before replacing the key.
- Managed-key deletion, spend resets and Advanced spend edits are blocked while
  enforcement is on. An empty key roster retains observed consumed spend rather
  than treating deletion as a period reset. Direct upstream changes and loss of
  process history still require operator review; this is not a durable spend ledger.
- Each pass uses one fixed set of shares. A sign-in or budget edit during a pass
  applies on the next pass, about a minute later; it never caps a key at zero.
  A temporary synchronization error does not remove a member from the split.
- Budget writes lock only the groups they can change: the member's current
  group, the group they came from and any group holding their key. Each reads
  only those members' keys, so sign-ins and key replacements in different groups
  run in parallel, and the minute-by-minute synchronization releases each group
  before the next. A returning member whose group and share are unchanged signs
  in without a budget pass. After an assigned total changes (money moves between
  groups), operations read and lower every member first until the next full
  synchronization has applied it.
- A member moved to another managed group keeps their key: sign-in or the next
  synchronization moves it to the new group. Consumed spend follows the member,
  so the new group counts it and the previous group's share is released to its
  remaining members. First-time provisioning
  records the identity and participant under the same serialization lock before
  collecting spend. Deficit snapshots refresh their fallback spend floors even
  when allocation totals remain unchanged.
  Incomplete key records are hydrated through key-info and ownership is verified.
  An omitted source team stops writes if hydration cannot establish it; only an
  explicit `null` means the key is unassigned.
- Manual overrides saved for someone who has not signed in stay saved but
  inactive, and apply when that person first signs in. That can push the group
  into a deficit, which the Budget planning page shows. If manual values exceed the group amount, automatic
  members are held at their current spend until an administrator fixes it.
- Each key keeps its own `duration` reset, so a group's total holds within each
  member's budget period rather than one aligned period. Until the next pass,
  existing members keep their previous, larger share after a newcomer joins.

Strict hierarchical enforcement remains unfinished: aligned reset/transfer
accounting and all supported request-path reservation guarantees must be verified
before native limits are activated. An Enterprise license alone does not prove
those conditions. The local 1.109.1 gateway accepts ordinary member budget updates
without a license, but unknown-priced/image/audio/batch workloads need separate
validation. Neither polling nor a LiteGate configuration lock enforces inference.

## Removed group retirement

Cleanup currently means an opt-in **assessment and audit**, not automatic deletion.
LiteGate records ownership only when its own create request is confirmed; it
never adopts pre-existing/operator teams as disposable. Removed owned teams are
checked for current configuration, local identity, remote membership, and key
references. Unknown/incomplete checks are retained for review.

The upstream team-delete contract cannot condition deletion on still being empty.
Deleting after an empty snapshot can race another actor adding a member or key.
Automatic deletion therefore remains unfinished; the assessment records
`review_required`, including `atomic_delete_unavailable` for an otherwise empty
candidate, without risking unrelated records. The assessment runs with each
reconciliation pass, but a candidate is audited only when first found or when its
reason changes (and once more after an application restart).

## Startup and upgrade reliability

Startup initializes SQLite under a bounded write reservation and atomically
advances `PRAGMA user_version`. It adopts existing unversioned data without
rewriting users, keys, or SSO identities. Already applied migrations are skipped.
Ordinary reads/authentication/audit writes and readiness checks do not issue DDL;
connection contexts now close their handles. Failed migrations roll back.

Organization reconciliation remains separate and runs every 60 seconds. Its
warnings concern upstream policy synchronization, not repeated SQLite schema
migrations. The specific reported crash after three attempts has not been
reproduced; capture the actual traceback and previous-container events before
attributing it to a schema migration.
