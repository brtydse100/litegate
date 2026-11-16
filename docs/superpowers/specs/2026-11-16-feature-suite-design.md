# LiteGate feature suite and local SSO validation

Status: approved design. See the [validation report](../../feature-suite-validation.md)
for implementation coverage, recorded checks and unfinished requirements.

Ruling after approval: core LiteGate functionality must work with or without a
LiteLLM Enterprise license. Operator-configured LiteGate group administrators
provide scoped authority independently of native licensed team-admin roles.
Designation is still separately required. Native team administration remains an
additional compatible authority source, never a required license bypass.

## Intent and baseline

Implement the ten requested improvements against current upstream main
`5b9ee7c6b6bbc70cd958549cc975c717eaff9fc5` (2.18.0), retaining LiteGate's
management-only architecture and LiteLLM's ownership of request routing and spend.
Preserve the existing 2.12.0 checkout and all its uncommitted changes. Use a
separate branch/worktree for implementation; do not commit, push, publish, or
open a PR without explicit authorization.

Subsequent user authorization permits continuing implementation, opening a PR
and preparing 2.19. Publication remains a separate action.

Helm, Docker/Compose, environment variables, configuration documentation, API
documentation, tests, and browser-only demo behavior must remain consistent.
No new production runtime dependency or service is proposed. Keycloak is an
explicitly requested local test service, never a production dependency.

## Established findings

- Saved-key storage appeared in 2.11.0. The same synthetic SQLite record was
  readable by all 14 releases through 2.18.0 and current main. Disabling storage
  or changing the database makes recovery unavailable without invalidating the
  upstream credential. Deployment persistence is disabled in the reported Helm
  installation; whether another durable mount exists remains unverified.
- Identifier replacement in live key metadata broke lookup in 2.15.3 and was
  corrected in 2.15.4. Retain that fix and existing ownership checks.
- Email truncation lacks consistent full-address/copy access.
- Advanced frontend validation implements fewer JSON Schema constraints than
  the backend, whose generic rejection hides the failing field. No evidence
  justifies relaxing a real policy constraint.
- Local-users endpoints intentionally exclude SSO accounts. Organization views
  contain mapped identities, not all registered people.
- Normal database operations repeat idempotent schema creation. Organization
  reconciliation separately retries every 60 seconds. No specific three-attempt
  startup crash has been reproduced.
- Organization access is global-admin only. Personal hourly analytics,
  delegated budgeting, and equal allocation are missing.
- Existing groupTotal is reporting-only. Existing synchronization removes native
  team/member/user caps after enforcing per-key allowances. Strict hierarchical
  enforcement must not be claimed from that behavior.

## Approaches and recommendation

1. Extend the existing management layer, persist small control/analytics tables
   in its SQLite database, and use verified native LiteLLM enforcement. This
   preserves the deployment model and is recommended, with a compatibility gate
   before enabling strict hierarchical budget management.
2. Map the entire hierarchy to native LiteLLM organizations/teams. This requires
   licensed features in some cases and cannot represent arbitrary eight-level
   nested teams faithfully, so it does not cover the requested hierarchy.
3. Route inference through a new LiteGate gateway or add an upstream request
   hook. This could provide broader enforcement but introduces a new request
   path and substantially more operational surface. It is outside this proposal.

## Delivery sequence

### A. Local integration environment and reliability

Reuse the pinned LiteLLM/PostgreSQL integration stack. Add a local-only Keycloak
realm with a confidential OIDC client, exact loopback callback, signed ID tokens,
groups mapper, and synthetic accounts. Tests must exercise authorization-code
login, state/nonce/signature verification, and actual backend permission checks.
Never disable TLS verification globally or connect the public demo to this stack.

Centralize SQLite schema setup during startup, including existing organization
and identity tables. Use a schema version and a bounded BEGIN IMMEDIATE write
reservation; changes and version advancement commit together. Do not issue DDL
on reads, authentication, key annotation, audit writes, or readiness checks.
Keep foreign keys enabled, short connections, and explicit startup failure logs.
Preserve fail-closed organization policy behavior while synchronization is pending.
Do not label the reported crash fixed without reproducing its actual condition.

Explain persistent storage for SSO-only installations in both Helm and Docker
guides. Warn clearly when recoverable-key storage uses an explicitly ephemeral
deployment; do not silently change a user's existing volume or move its database.
Test restart/upgrade recovery on the same volume and loss-of-copy behavior on
an empty volume without generating or invalidating upstream credentials.

### B. Email, Advanced errors, people directory, and key regressions

Use one small accessible email component: selectable full wrapping address,
explicit copy action, and copied/error status. Cover sidebar, users, team members,
organization rows, and other email-bearing lists at desktop/mobile widths.

Keep backend validation authoritative and equally strict. Return bounded field
and nested-path errors that explain the failed constraint without echoing values,
credentials, or arbitrary upstream error text. Retain drafts and associate errors
with the corresponding accessible frontend controls. Do not hand-build an entire
JSON Schema implementation or introduce a validation dependency without approval.

Add a separate paginated, searchable read-only people-directory endpoint using
LiteLLM's existing user-list contract. Preserve existing local-account API shapes
and keep password/role account actions on local rows. Include SSO and no-key
accounts in permitted lists; ordinary users cannot gain the admin directory.
Personal membership/key views derive their subject from the authenticated account.

Retain stable canonical identity and original key identifiers through metadata
refreshes, login, group migration, restart, and regeneration. Hashes remain lookup
identifiers, never plaintext secrets. Missing stored copies show clear status.

### C. Organization access and safe retirement

Introduce organization-scoped capability resolution separate from global admin.
Delegated users must both be designated by canonical user ID in configuration
and currently administer the relevant LiteLLM team. Recheck on every request;
unknown/unavailable authority fails closed. Allow multiple explicitly authorized
subtrees. Designation plus current administration of an authorized root confers
access throughout that subtree; native administration of every descendant is not
required. Existing global admins retain full access; key-authenticated identities
remain excluded from administrative/delegated operations.

Apply scope before returning groups, users, usage, totals, errors, breadcrumbs, or
parent metadata. Omitted group parameters resolve to authorized roots, never all
groups. Hide inaccessible navigation and enforce the same boundary in the API.
Mirror designation configuration in Helm values/schema, YAML, and environment.

Track durable ownership only for teams this installation actually creates.
Do not infer ownership from an ID prefix or adopt operator teams as deletable.
Retire removed managed groups only when complete remote and local checks prove
no users, keys, identity assignments, current configuration references, or other
dependencies remain. Skip uncertain checks, audit outcomes, and use upstream
transactional deletion safeguards if available. Never promise an atomic local plus
remote transaction. Existing teams without ownership evidence require review.

### D. Personal analytics

Record canonical portal identities independently of hierarchy/key creation.
Schedule one non-overlapping hourly aggregation pass with bounded concurrency.
Use complete daily aggregate APIs, not raw spend-log scans. Prefer a verified
global batch contract; otherwise batch known users through bounded per-user
aggregate requests during the scheduled pass, never dashboard loads.

Persist per-user/day/model totals and last successful refresh in existing SQLite,
indexed by owner/date. Refresh a bounded 90-day window; expose that coverage.
Atomically publish each complete user's snapshot and retain the last good data
after failure. Validate separate input/output tokens; unavailable is not zero.
Show requests, token metrics, costs, daily/model breakdowns, freshness, and actual
budget metadata. Keep independent key/reset allowances distinct if they cannot
be truthfully represented as one personal budget.

Personal endpoint queries always filter by current_user.user_id, including
freshness/errors, and accept no owner selector. Ordinary users receive the page.
No opening of a dashboard initiates a remote analytics scan.

### E. Hierarchical allocation and enforcement

Keep legacy informational groupTotal/perUser behavior by default. Introduce
explicit opt-in budget management, with durable policy revisions and manual
overrides in SQLite. Document the new persistent control state and upgrade path.

For each group's envelope reserve immediate child envelopes and manual DIRECT
user allocations. Equally split the residual among automatic direct users;
children allocate recursively. Use fixed-precision monetary units, deterministic
rounding, and retain the remainder. Never count descendant users twice.
Child envelopes are explicitly assigned, not equal-share participants; a new child
without an assigned envelope reserves zero in this opt-in mode. Equal automatic
distribution applies to users as requested, not to child groups. Activation must
validate existing child assignments and allocations before changing legacy policy.
NULL means automatic; zero is an explicit manual allocation. Preserve overrides.
Recalculate immediately on authorized membership/parent changes while retaining
already consumed period spend for removed/moved users. Reject over-allocation.

Group admins can edit direct users and descendant child envelopes in their scope,
but cannot edit the assigned envelope of their authorization root through that
root's capability. A separately authorized parent scope or system administrator
may set that envelope. Proposed default:
delegates cannot raise their own personal allowance; a parent/system admin must.

Serialize allocation edits transactionally with policy revision checks. Persist
pending upstream changes and apply/verify decreases before increases. Do not
display a policy as enforced until native readback confirms it; retry partial
failures safely without erasing existing restrictions or spend.

The minimal enforcement approach conserves allocations down to native aggregate
team-member allowances, protecting users with multiple keys, and retains native
team caps as defense. Require synchronized period boundaries and retention of
spent allocations across transfers. Verify the actual pinned LiteLLM version,
license, native budget contracts, and request cost reservations before activation.
LiteGate asyncio locks protect management edits, not concurrent inference.

Current upstream reservations have limitations for token-unknown/image/audio and
batch workloads. Tests must establish the supported request set and fail-closed
behavior. If native capabilities cannot enforce the requested guarantees, keep
strict mode unavailable and report the exact limitation; do not silently claim
polling or per-key ceilings enforce every ancestor. Broader gateway/hook work
requires a separate architecture decision.

## Proposed configuration surface

Finalize exact names in implementation plans. Provide equivalent backend YAML,
uppercase environment, Helm values/schema/templates, Compose examples, and docs
for scoped organization designation, analytics enablement/retention/concurrency,
safe owned-team cleanup, and opt-in hierarchical management. Hourly refresh is
the production default; tests use an injected clock rather than production polling
shortcuts. Preserve existing settings and default authorization boundaries.

## Validation and completion

- Unit/API tests: schema upgrade/rollback/concurrent startup; all authorization
  actor types; subtree isolation; directory/search without keys; sanitized nested
  validation; preservation of original key identifiers and stored copies.
- Analytics: complete pagination, token metric availability, restart persistence,
  hourly scheduling, failure retention, lightweight reads, cross-user isolation.
- Budgets: manual/auto/zero/rounding, nested reservations, conflicting edits,
  transfers/spend/reset windows, multiple keys/rotation, partial upstream failure.
- Actual Keycloak: global admin, designated group admin, ordinary/no-key user,
  outsider, designated nonadmin, undesignated admin, group change and revocation.
- Actual LiteLLM: signed-in ownership, original credential inference after group
  change/restart, and parallel near-cap requests for supported strict-mode paths.
- Frontend mobile/desktop, browser-only demo, format/lint/typecheck/unit/build;
  backend formatting/full tests; Helm render/lint/schema and Docker image build;
  repository version/docs checks. No checks replaced by disabled rules.

Each delivery stage must be independently testable. Final handoff lists changed
files, exact checks/results, settings, compatibility requirements, and any actual
unresolved limitation. Do not describe every requested feature as complete merely
because existing regression suites pass.
