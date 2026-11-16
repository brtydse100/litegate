# Governance, analytics, and local SSO implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development to execute independently owned tasks, with tests and review.

**Goal:** Implement the approved feature suite without weakening authorization or inventing inference guarantees.

**Architecture:** Retain FastAPI/React, existing SQLite and LiteLLM management contracts. Isolate new services; one application process. No additional production dependencies or inference gateway.

**Tech Stack:** Existing Python, SQLite, React, TypeScript, pytest, Vitest, Playwright, Helm, Docker; local Keycloak test container.

**Spec:** [Approved design](../specs/2026-11-16-feature-suite-design.md).

This records the approved initial implementation plan. The execution record and
[validation report](../../feature-suite-validation.md) describe delivered work
and remaining capability gates; the original checklist is retained as planned scope.

## Global constraints and rulings

- Preserve dirty original checkout. Implement only in this worktree, based on upstream 2.18.0.
- The initial implementation phase prohibited commits, pushes and PR creation.
  Later user authorization permits continuing the changes, opening a PR and
  preparing 2.19; it does not authorize publication. No new runtime dependencies
  or real credentials.
- New Python modules stay below 400 lines. Do not refactor unrelated oversized modules.
- Independent agents own disjoint files. Root owns main.py/config.py, deployment configuration and integration.
- Every behavioral task starts with meaningful failing tests. Preserve existing tests unless the approved public contract intentionally changes.
- Feature configuration must have matching YAML/environment/Helm/Docker docs. Existing default behavior remains compatible.
- Strict budgets are opt-in and capability-gated; unknown capabilities never count as verified enforcement.

## Review focus

Check cross-subtree leakage in totals/errors; stale group-admin revocation; old SQLite upgrade rollback; analytics failed-refresh retention and owner isolation; concurrent allocation/partial native writes. Test actual supported request-time enforcement separately from management edits.

## Task 1: Database initialization and ownership-safe cleanup

Files: local_users.py, organization_store.py, sso_identity.py, key_secrets.py, audit.py; new database service and tests. Root integrates startup call.

- [ ] Reproduce DDL during ordinary reads, repeated/concurrent startup and old database preservation.
- [ ] Implement versioned BEGIN IMMEDIATE startup initialization; remove DDL from ordinary reads and readiness; explicitly close connections.
- [ ] Preserve public store interfaces/test setup through one initializer fixture; verify rollback and bounded lock failure.
- [ ] Report startup integration instructions; root owns analytics/budget table initialization.

## Task 2: UI, field-specific Advanced errors, and people directory

Files: shared EmailAddress component, affected existing UI, policy_schemas.py, new people directory API/service/tests. Root registers directory router.

- [ ] Add failing UI tests for complete/copyable long email and value-free nested server errors.
- [ ] Implement shared accessible email display, authoritative structured errors, and draft preservation.
- [ ] Add paginated read-only admin directory through existing LiteLLM /user/list; preserve local-account contracts and reject ordinary/key actors.
- [ ] Verify self/SSO/no-key identities, server-side bounded search, and original key metadata regressions.

## Task 3: Organization scope and retirement

Files: organization router/reports; new organization_access and organization_retirement services and tests. Root owns settings and Home route integration.

- [ ] Add failing actor/subtree/revocation tests before scoped service changes.
- [ ] Resolve designation plus live team admin membership; return permitted roots and enforce scope for every response field.
- [ ] Keep system admin behavior, deny key identities, and avoid leaking all groups for omitted scope.
- [ ] Record only newly created team ownership; retire only proven owned/removed/empty/unreferenced teams; audit skips/failures.

## Task 4: Personal analytics

Files: new analytics store/service/router, PersonalAnalytics UI, API types/client, tests. Root owns this task.

- [ ] Test atomic stored snapshots, owner isolation, empty/unavailable metrics, and failure retention.
- [ ] Implement indexed canonical-user registry and daily/model snapshot schema; no remote queries on dashboard reads.
- [ ] Implement bounded hourly aggregation from complete upstream daily aggregates, including input/output metrics and current budget metadata.
- [ ] Expose self-only endpoint and ordinary-user navigation with freshness, time/model charts and unavailable/stale states.

## Task 5: Budget allocation and management

Files: new budget policy/store/allocation/native adapter/router/UI and tests; minimal organization synchronization integration.

- [ ] Test integer allocation, children/manual reservations, zero/auto, concurrent revisions, scope and own-root restrictions.
- [ ] Implement opt-in durable envelopes/overrides and consumed-period reservation; preserve legacy policy by default.
- [ ] Persist pending native updates, verify decreases before increases, retain failed-state diagnostics.
- [ ] Verify native aggregate team-member budgets and supported request reservations against pinned LiteLLM; keep strict activation unavailable when not verified.
- [ ] Add scoped budget editor with assigned/allocated/used/remaining and auto/manual/pending status.

## Task 6: Deployment parity and documentation

- [ ] Add typed settings, validation, env/YAML samples, Helm defaults/schema/templates and Compose examples for every feature.
- [ ] Document SSO SQLite persistence and upgrade backup/migration; do not auto-transfer an ephemeral live database.
- [ ] Update API, organization, configuration, testing and deployment docs; retain browser-only synthetic demo.

## Task 7: Keycloak and actual integration

- [ ] Check local Keycloak authorization-code login through LiteGate without bypassing state/nonce/signature checks.
- [ ] Add reproducible synthetic realm/Compose override and Playwright config/spec for all permission personas.
- [ ] Exercise no-key discovery, group changes, key preservation after restart, scoped API denial, analytics isolation, and supported budget concurrency.

## Task 8: Review and handoff

- [ ] Review each independent task and integrated branch; fix material findings.
- [ ] Run backend formatting/full tests; frontend format/lint/typecheck/unit/build and relevant browser tests.
- [ ] Run Helm lint/render tests, Docker build, version/docs checks and actual integration where available.
- [ ] Document exact changed files/checks, settings, breaking changes, unsupported cases, and any unreproduced production crash. Do not claim gated requirements implemented when unavailable.


## Execution record

- Independent implementation and review subagents worked in the shared isolated
  checkout during the initial implementation phase.
- Tasks 1 through 4, 6 and 7 have implementation and validation coverage, with
  automatic upstream deletion in Task 3 explicitly unfinished. Task 5 provides
  safe proposal and preview behavior; strict live hierarchical enforcement remains
  unfinished. Both limitations follow the design's capability and safety gates.
- Ruling: later user instruction requires license-independent core behavior.
  Added operator-configured LiteGate group administrators alongside optional
  native authority; designation remains a separate requirement. This does not
  grant global administration or bypass an upstream license check.
- Three initial agents hit a provider usage limit; root preserved their edits
  and completed integration. Subsequent parallel reviews succeeded.
- Final review's analytics publication/read race was reproduced with actual
  SQLite and fixed using a shared read transaction. Other findings and checks
  are recorded in the [validation report](../../feature-suite-validation.md).
