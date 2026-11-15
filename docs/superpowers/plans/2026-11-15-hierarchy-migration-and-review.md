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
