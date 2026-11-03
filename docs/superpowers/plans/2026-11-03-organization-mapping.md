# Email Organization Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Implement in this session; delegation is unnecessary for these coupled changes.

**Goal:** Add optional email-based team hierarchy provisioning to existing SSO, including keyless creation before first login and automatic identity linking.

**Architecture:** A validated `levels` array organizes named groups and resolves email and existing SSO team assignments into direct and ancestor memberships. Normalize it into the same resolver as the original supported flat format. Focused services provision LiteLLM users and store only identity/reservation bookkeeping in the existing SQLite database. Existing membership and key migration services remain the execution path.

**Tech Stack:** Existing FastAPI, Pydantic settings, Python standard-library JSON/SQLite, HTTPX, pytest, Docker Compose, Helm. No new dependency.

**Spec:** [Organization mapping design](../specs/2026-11-03-organization-mapping-design.md).

## Global Constraints

- User-approved schema update: use `levels -> groups`, without an outer `groups`.
  Add normalization/validation tests and update JSON, YAML, Helm, and PR examples.
  Keep flat mappings compatible; parent links and all identity behavior remain unchanged.

- Original implementation and the spec's identity revision approved; the revision supersedes conflicting task steps below.
- User requested agents, an independent reviewer, and a PR. Use the prepared isolated branch, review before opening the PR, and commit/push only feature work.
- No new dependency, service, UI, local password, or automatically generated key.
- Preserve all existing uncommitted parent-checkout work.
- Keep new Python files below 400 lines; do not refactor unrelated code.
- Preserve authentication, CSRF, rate limits, headers, audit, and administrative boundaries.
- Existing SSO user IDs, keys, mapping precedence, and default teams remain compatible.
- Configuration adds memberships; it does not automatically revoke memberships.
- Configuration changes take effect after restart or Helm rollout.

## Approved identity revision: task amendments

These amendments supersede safe-retirement and strict pending-startup steps in
Tasks 2, 3, and 5. The user approved these amendments and the spec revision.

- Task 2: remove all user-delete/retirement operations. Implement durable
  superseded-reservation bookkeeping and retry recovery. Verify exact-ID remote
  ownership markers, ordinary keyless creation, duplicate handling, complete
  paginated lookup, and membership contracts. Report Docker unavailability as
  unavailable live validation, not a passing integration result.
- Task 2: implement a pending state for a single unproven ordinary existing
  account; make no remote mutations for that account and allow startup to serve
  login while reporting it pending. Existing local/admin email-only conflicts,
  ambiguous matches, incomplete scans, and actual provisioning failures remain
  errors. Preserve established administrative SSO login behavior.
- Task 3: test legacy-subject proof resolves pending identity; mismatches fail
  without mutation. Test different provider authorities and competing subjects,
  ownership-marker mismatches, durable binding before remote membership writes,
  and no silent switch after binding.
- Tasks 2/3: test zero delete calls even if an independent LiteLLM client adds
  keys to a superseded reservation. Verify its memberships, budget, keys, and
  history remain untouched; canonical provisioning and migration use only the
  selected user ID. Restart must not create another reservation.
- Task 3: retain canonical bindings when mapping is removed; verify existing
  provisioned accounts remain accessible without affecting never-configured
  installations.
- Task 4: document pending confirmation and retained visible remote records,
  including possible user-count/license impact and the fact that superseded
  bookkeeping does not disable a LiteLLM account.
- Task 5: independent review must verify these revised acceptance cases before
  the feature-only branch is pushed and its PR is opened.

## Review Focus

1. Existing SSO accounts and same-email local accounts must not be merged or duplicated silently: Task 2 contract tests and Task 3 login tests.
2. A crash between remote user creation and local binding must recover on retry without generating keys: Task 2 retry tests.
3. Reused emails, conflicting subjects, and explicitly unverified emails must not claim another identity: Task 3 security tests.
4. Multiple direct groups and overlap with old SSO mappings must preserve deterministic primary teams: Task 1 resolution tests and Task 3 migration tests.
5. A missing file, invalid hierarchy, missing team, or failed provisioning must not look like successful synchronization: Tasks 1, 2, and 4 failure tests.

---

### Task 1: Configuration and hierarchy resolution

**Files:**
- Create `backend/app/services/organization_mapping.py`.
- Modify `backend/app/config.py` with optional inline/file settings only.
- Create `backend/tests/test_organization_mapping.py`.

**Interfaces:**
- `load_mapping(inline: dict, filename: str) -> OrganizationMapping` validates one source into an immutable per-process snapshot.
- `OrganizationMapping.team_ids(email: str, sso_team_ids: list[str]) -> list[str]` returns ordered direct/inherited teams; the caller appends the existing default team.
- `OrganizationMapping.member_emails() -> list[str]` returns normalized configured emails in declaration order.
- `OrganizationMapping.referenced_team_ids() -> list[str]` returns distinct team IDs for preflight checks.

- [ ] Write tests for empty config, equivalent JSON/inline input, inline and multiline lists, case/whitespace normalization, three-level inheritance, parent-only membership, duplicate emails, multiple groups, and old SSO teams with ancestors.
- [ ] Pin ordering: an existing SSO primary stays primary; with no SSO match, platform beats engineering by depth; equal-depth direct assignments use declaration order.
- [ ] Add rejection tests for cycles, missing parents, unknown fields, repeated team IDs, malformed/missing files, and conflicting nonempty sources.
- [ ] Run `python -m pytest tests/test_organization_mapping.py -v` from `backend`; confirm the new behavior fails before implementation.
- [ ] Implement typed schema validation and deterministic ancestor traversal using existing dependencies. Resolve file paths against the backend directory.
- [ ] Run the focused tests and existing SSO configuration tests; confirm they pass without changing unconfigured behavior.

### Task 2: Keyless provisioning and durable identity bookkeeping

**Files:**
- Create `backend/app/services/sso_identity.py` for SQLite reservations/bindings.
- Create `backend/app/services/organization_provisioning.py` for remote provisioning.
- Modify `backend/app/main.py` at lifespan and readiness integration points.
- Add `backend/app/services/litellm_identity.py` for the narrowly required remote identity operations, reusing `litellm_client`.
- Create `backend/tests/test_organization_provisioning.py` and `backend/tests/test_sso_identity.py`.
- Extend `backend/tests/integration/test_litellm_live.py` or a focused adjacent integration file if needed to respect the line limit.

**Interfaces:**
- `initialize_identity_store() -> None` creates its own table using the existing SQLite connection utility; no local-account records or passwords.
- `provision_members(mapping: OrganizationMapping) -> None` validates remote teams, reserves/recovers configured users, and adds direct/inherited memberships.
- `resolve_sso_user_id(provider: str, subject: str, email: str) -> str` is async; preserves an existing subject account or returns the feature-owned canonical reserved account and persists the binding.
- Use `sqlite3` transactions and unique provider/subject and provider/email constraints. Do remote calls outside database transactions; checkpoint durable intent before remote writes and reconcile on retry.

- [ ] Inspect the pinned LiteLLM integration service to establish exact email lookup, account metadata/role, and keyless reservation retirement contracts. Add live contract tests; do not invent endpoint filters or response shapes.
- [ ] If these contracts cannot support the design, stop for a narrowly scoped design revision before identity implementation.
- [ ] Write tests for automatic table creation, preserving existing database rows, no mapping/no work, all-team preflight before writes, existing SSO IDs, local/admin email conflicts, duplicate email accounts, and keyless creation payloads.
- [ ] Add retry tests at each remote/local boundary, concurrent duplicate reservations, partial team failures, existing keys on a reservation, and restart after canonical rebinding.
- [ ] Run these tests to observe failures, then implement the smallest reservation/binding and provisioning services.
- [ ] Add audit events for provisioning, binding, and failures without tokens or key secrets; use bounded sequential remote work and fail the configured startup pass on incomplete provisioning so restart retries it.
- [ ] Connect startup after existing SQLite/client initialization; close the HTTP client even if provisioning fails. Keep existing health behavior when the feature is absent.
- [ ] Re-run focused unit tests and the pinned live contracts; verify no key is created and no original account/key is deleted.

### Task 3: Compose mapping with both SSO login flows

**Files:**
- Modify `backend/app/routers/auth.py`, preserving the working-tree key migration changes.
- Create `backend/tests/test_organization_sso.py`.
- Extend existing SSO/key migration tests only where they exercise the new integration.

**Interfaces:**
- Consume Task 1's loaded snapshot and Task 2's `resolve_sso_user_id`.
- Continue calling `litellm.sync_user_team_memberships` and `key_team_migration.migrate_user_keys` with the canonical user ID and ordered primary team.

- [ ] Write OIDC and generic SSO tests for email-only mapping, old/new mapping union, inherited SSO teams, default team ordering, and mapping-required acceptance from either source.
- [ ] Add tests for first-login binding, existing subject-based accounts with keys, same-email local/admin isolation, subject mismatch on a bound reservation, explicitly unverified email, and absent email claims.
- [ ] Pin compatibility: no mapping preserves original subject IDs and behavior; role assignment is unchanged; ancestor teams never override the primary; manual memberships are retained.
- [ ] Run focused tests to observe failures; integrate resolution only when configured, after provider authentication and before provisioning/session creation.
- [ ] Use existing key migration for the canonical account on login; never generate a key during reservation or binding.
- [ ] Run the SSO, team, dependency/session, and key migration suites; confirm unchanged security checks and existing sessions remain usable.

### Task 4: Docker/Helm configuration and operator documentation

**Files:**
- Modify `deploy/docker-compose/config.yaml` and document optional read-only mounts for both source-build and image Compose deployments.
- Modify `deploy/helm/litegate/values.yaml`, `templates/configmap.yaml`, and `templates/deployment.yaml`.
- Create `scripts/test_organization_mapping_helm.py` following the existing Helm test pattern.
- Update `.env.example`, `docs/configuration.md`, `docs/authentication.md`, `docs/features.md`, and the focused deployment documentation as necessary.
- Update `API.md` to describe mapping-required behavior and canonical session IDs, without adding endpoints.

**Interfaces:**
- Emit `ORGANIZATION_MAPPING` from `config.organizationMapping` using `toJson`.
- Emit `ORGANIZATION_MAPPING_FILE` from `config.organizationMappingFile`.
- Use existing `extraVolumes`/`extraVolumeMounts` for Helm JSON files; no new mount abstraction.
- Add a pod-template checksum for organization mapping values so inline edits trigger rollout. Externally managed file changes require explicit restart.

- [ ] Add Helm render tests for defaults, inline lists, equivalent JSON, empty inline/file selection, source conflict, existing SSO variables, and changed pod checksum.
- [ ] Run `python -m unittest scripts/test_organization_mapping_helm.py` to observe failures, then add the minimal values/templates and rerun it.
- [ ] Document exact JSON/Helm examples, pre-existing team prerequisites, additive membership semantics, primary ordering, keyless provisioning, automatic SQLite initialization, trusted email requirements, and identity conflict recovery.
- [ ] Document Docker mount `./organization.json:/app/backend/organization.json:ro` with `organization_mapping_file: /app/backend/organization.json`; mount is optional and absent from the default running configuration.
- [ ] Include a Helm file alternative using an existing ConfigMap and existing volume extension points. Do not require inline and file data simultaneously.

### Task 5: Verification and reviewable handoff

- [ ] Check the final diff against the starting dirty worktree; verify no unrelated edits or changed dependencies, no secrets, no commits/pushes, and all new Python files under 400 lines.
- [ ] From `backend`, run `python -m ruff format --check .` and `python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=75`.
- [ ] From `frontend`, run `npm run format:check`, `npm run lint`, and `npm run typecheck`; preserve unrelated user changes and report any pre-existing failures separately.
- [ ] Run `python scripts/version.py --check`, `python scripts/check_docs.py`, `helm lint deploy/helm/litegate`, and both existing/new Helm render test scripts.
- [ ] Run the pinned live LiteLLM integration contracts and Docker image build when tooling is available. Clearly report unavailable checks rather than claiming success.
- [ ] Review first-time and existing-user scenarios, startup retry, email reuse, and combined mapping precedence against the spec. Hand back the diff and results for user review.

## Mock configuration examples

All team IDs below are mock references to already-existing LiteLLM teams.

JSON file `organization.json`:

```json
{
  "levels": [
    {
      "name": "companies",
      "groups": {
        "company": {
          "team_id": "team-company",
          "members": ["jordan@example.com"]
        }
      }
    },
    {
      "name": "departments",
      "groups": {
        "engineering": {
          "team_id": "team-engineering",
          "parent": "company",
          "members": ["sam@example.com"]
        }
      }
    },
    {
      "name": "teams",
      "groups": {
        "platform": {
          "team_id": "team-platform",
          "parent": "engineering",
          "members": ["alice@example.com", "bob@example.com"]
        }
      }
    }
  ]
}
```

Equivalent inline Helm values:

```yaml
config:
  organizationMapping:
    levels:
      - name: companies
        groups:
          company:
            team_id: team-company
            members: [jordan@example.com]
      - name: departments
        groups:
          engineering:
            team_id: team-engineering
            parent: company
            members: [sam@example.com]
      - name: teams
        groups:
          platform:
            team_id: team-platform
            parent: engineering
            members: [alice@example.com, bob@example.com]
```

Alice and Bob join Platform, Engineering, and Company. Sam joins Engineering
and Company. Jordan joins Company only. Existing SSO group mappings may add
further memberships and keep their primary-team precedence.
