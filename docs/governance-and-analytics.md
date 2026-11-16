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
supported. Backend checks run on every request; native lookup failure grants
nothing. Configuration changes require the usual application restart/rollout.

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

Usage spend displays use six to ten decimal places; amounts below that precision
use scientific notation so a nonzero prompt cost is never displayed as zero.

The opt-in budget page currently stores **proposals**. It does not activate a
new enforcement mode. Child envelopes and manual direct-user overrides reserve
funds first; the remainder is divided equally among other direct users using
integer micro-dollars. Children allocate recursively; descendant users are not
counted twice. Zero is a manual zero allocation; a blank override means automatic.
Manual overrides persist across recalculation. Conflicting revision edits and
over-allocation are rejected transactionally. Delegates cannot edit their scoped
root envelope or raise their own personal allowance, including indirectly.

Invalid legacy proposals remain visible with a group-specific allocation error.
Automatic shares and allocation totals are unavailable until repaired; explicit
overrides remain visible. System administrators may repair independent deficits
incrementally, provided no group's deficit increases. Delegated edits require a
valid allocation throughout.

Existing per-key enforcement remains active. The page reports unknown used and
remaining amounts as unavailable and marks proposals as not applied. Activation
returns 503. A native adapter and durable apply journal are covered by contract
tests, including aggregate member caps and verified decreases before increases.
They are not called from proposal editing.

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
candidate, without risking unrelated records.

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
