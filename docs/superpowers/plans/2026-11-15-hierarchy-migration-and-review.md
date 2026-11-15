# Hierarchy migration and review implementation plan

> Execute inline with superpowers:executing-plans and test-driven-development.

**Goal:** Deliver the approved review fixes and automatic migration into LiteGate's existing organization hierarchy in one PR based on v2.18.0.

**Architecture:** Extend the existing authentication, rotation, query-cache and reconciliation paths. Reuse the current SQLite identity records and LiteLLM APIs; introduce no dependency or service.

**Spec:** The user-approved six-step scope in this conversation: revalidate findings, fix remaining bugs, adopt existing identities/keys automatically, preserve credentials and spend while applying hierarchy policy, resume failures safely, test/document and open a PR.

## Global constraints

- Preserve unrelated work in the original checkout.
- Keep Python files below 400 lines; avoid unrelated refactors.
- Preserve authentication, CSRF, role boundaries, audit behavior and key secrecy.
- Do not create or merge users by email, replace keys during migration, or reset spend.
- Publish an immutable PR preview tag/image for the final validated head; do not merge or release.

## Review focus

- Bootstrap/database username collisions, including old signed sessions and configuration changes.
- Rotation retaining blocked/model/rate/team/expiry policy and rejecting incompatible multiple-key policies.
- Account changes with cached queries and requests still in flight.
- Several users sharing old team caps: protect every key before removing caps, and finish within one pass.
- Retry after partial migration, with no key creation/deletion or spend reset.

## Tasks

1. **Authentication and audit:** Add failing HTTP tests in `backend/tests/test_review_security.py`; reserve the configured bootstrap username in `local_users.create_user`, distinguish new bootstrap sessions, reject ambiguous legacy sessions, and audit legacy account mutations. Verify both route families and ordinary-user authorization.
2. **Rotation policy:** Add failing lifecycle tests in `backend/tests/test_rotation_policy.py`. Extract rotation into a focused service if required by the line limit; retain source non-budget restrictions and absolute expiration, preserve unmanaged budgets, and retain hierarchy-owned policy for managed users. Verify replacement policy before revoking source credentials; reject incompatible source policies safely.
3. **Browser account isolation:** Add failing `frontend/src/hooks/useAuth.test.tsx` covering logout, a second login, and delayed query responses. Cancel and clear cached queries/mutations before exposing another authenticated session.
4. **Automatic hierarchy migration:** Add failing first-pass and retry tests in `backend/tests/test_hierarchy_migration.py`. Separate the application of key policies from individual-cap finalization so shared native budgets cannot leave successfully migrated users pending until the next minute. Recheck persisted identity and live keys before finalizing; keep errors actionable and retryable.
5. **Delivery:** Update authentication, organization, feature and API documentation as applicable. Run backend coverage/format, frontend format/lint/typecheck/tests/build/audit, repository scripts and available Helm/container/browser checks. Obtain a fresh whole-branch review, resolve material findings, commit/push, open/link the PR, and publish/verify its immutable preview image.

## Execution notes

### Approved second-pass fixes

The user requested fixing all six subsequently reproduced findings. Add failing
regressions first, then implement and validate these changes in the same PR:

1. Permanent key deletion becomes administrator-only on both API families,
   including key-authenticated identities; personal rotation retains allowance.
   This closes reset/restriction bypasses without adding a local spend ledger.
2. Validate source teams outside the hierarchy before migration. Restrictive
   source policies require explicit administrator review rather than being lost.
3. Preserve MCP/tag rate controls, policies, prompts and related supported
   controls. Additional budget windows require assisted rotation to retain usage.
4. Lock administrator updates/deletions with rotation, recheck live ownership,
   and reject changed source policies before revocation (including external edits).
5. Return verified replacement expiration rather than stale generation metadata.
6. Keep process-local, configuration-scoped discovery issue snapshots and expose
   them through existing organization issue lists. No new database or service.

Run complete checks and a fresh independent review of these fixes before pushing.
Publish a new immutable preview tag/image; preserve the old preview artifact.

Second-pass execution: the 12 primary regression failures were reproduced before
implementation. The initial wider run exposed seven stale test contracts/mocks;
updated administrator authorization expectations and made unrestricted source
team fixtures explicit. The full suite then passed 724 backend tests and 119
frontend tests. A fresh independent review found two additional cases within the
same safeguards: source-team metadata-backed controls and budget-window/model
budget additions during rotation. Added seven failing parameterized cases, fixed
both guards and verified 26 focused tests. Full backend validation is being rerun.

Final follow-up validation: 731 backend tests passed, 4 opt-in live skips,
90.06% coverage; 119 frontend tests; 9 smoke and 2 demo browser tests passed.
Format, lint, typecheck, frontend build, zero-vulnerability production dependency
audit, 29 repository script tests, Helm lint, version and Markdown checks passed.
Both material independent-review findings were fixed with observed failing then
passing tests, followed by the complete backend coverage run. No deferred findings.

### Approved UI follow-up (2026-11-16)

The user requested addressing the subsequent four medium and three low UI
findings. Add failing tests before changes. Poll organization navigation/status
every 60 seconds and add manual refresh without eagerly fetching unselected
reports. Show reset-password errors/cooldowns inside the modal, clear stale
errors on reopening, and enforce the 256-character backend limit. Extend the
shared dialog hook with an explicit element ref, initial focus, Tab containment
and opener restoration; use it on password reset and existing modal callers.
Show known blocked/expired/budget states without claiming gateway health. Add
My key retry buttons, an accessible mobile sign-out name, and deployment-neutral
configuration wording. Retain the intentionally documented saved-key action flow.
Run frontend tests/checks/browser coverage and a fresh independent review, then
update PR49 and its immutable preview image. No dependency or backend contract
changes are needed.

UI execution: reproduced the UI regressions before implementation. The complete
frontend suite passed 131 tests after the initial fixes. A fresh independent
review found two material edge cases: manually refreshing All groups bypassed
the disabled detail query, and timezone-less expiration was interpreted in local
time instead of UTC. Each received a failing regression followed by its fix;
the complete suite then passed 133 tests. All 13 browser tests and 2 demo tests
passed; the password-reset keyboard test is now included in CI smoke coverage.
Format, lint, typecheck, production build, dependency audit (zero vulnerabilities),
backend formatting, 29 script tests, Helm lint, version and Markdown checks passed.

- Final: fixed All groups refresh requesting an empty group ID — regression RED→GREEN, suite 132/132.
- Final: fixed timezone-less expiration outside UTC — regression RED→GREEN, suite 133/133.
- Final: minor (deferred): removing an outer dialog while an inner dialog remains open can lose final opener restoration; no current UI callers nest dialogs.

- Baseline: 696 backend tests passed (4 live integration skips); 115 frontend tests passed.
- Task 1 complete: security/audit regressions observed failing, then 40 related tests passed.
- Task 2 complete: rotation regressions observed failing, then 43 related tests passed; budget preservation already present on main was retained.
- Task 3 complete: three account cache regressions observed failing, then passed after cancellation/clear and session generation checks.
- Task 4 complete: first-pass/retry migration tests observed failing, then 120 migration/hierarchy tests passed.
- Whole-branch independent review: no material findings; reviewer independently reran the 13 new backend and 3 frontend regressions.
- Compatibility follow-up: verified LiteLLM's pinned UpdateKeyRequest/handler source; expiration uses relative `duration`, not `expires`. Added a failing supported-API regression and passed it using a duration that never extends the original deadline (less than two seconds shorter). Added matching assertions to the existing opt-in live contract test.
- Final local validation: 711 backend tests passed, 4 live integration skips, 89.81% coverage; 118 frontend tests; 9 browser smoke and 2 demo tests; formatting, lint, typecheck, frontend build/audit (zero vulnerabilities), 29 repository-script tests, Helm lint, version and Markdown checks passed.
- Local Docker build/live integration unavailable because the Docker Desktop daemon is not running. CI owns the strengthened live rotation contract and the production image build; immutable preview publication is part of PR delivery.
- Ruling: use the existing hierarchy reconciliation and identity tables; startup already discovers configured exact IDs/emails, while SSO-group-only assignments require authenticated claims at login.
- Ruling: migration applies hierarchy-owned budgets intentionally; non-budget restrictions remain intact. Ambiguous identity or policy cannot be guessed automatically.
