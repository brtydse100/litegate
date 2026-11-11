# Dynamic editors and lazy organization implementation plan

**Goal:** Discover key/team settings from the installed LiteLLM and render the organization incrementally.

**Spec:** `docs/superpowers/specs/2026-11-12-dynamic-editors-and-lazy-organization.md`

**Architecture:** Bounded process-local OpenAPI cache, admin-only schema endpoint, jsonschema validation of opted-in changes, familiar controls plus Advanced. Add lightweight organization children/detail endpoints and fetch clicked branches on demand. No new persistent state or services.

## Tasks

- [x] Backend schema agent: add failure-first tests, approved jsonschema dependency, safe discovery/cache, schema endpoint, advanced_settings validation and protected merged updates. Check refs, unions/null, model budgets, MCP settings and authorization.
- [x] Frontend schema agent: reusable Advanced controls, opt-in edits and validation, key/team integration, unavailable-schema retry and selection reset tests.
- [x] Lazy organization agent: root-only and direct-child metadata endpoints, selected-team details, deferred usage/users, independently loaded navigation and demo helpers. Verify initial rendering before inner data and bounded reads.
- [x] Root: shared frontend client/types and demo routing; maintain synthetic demo support; document contracts, limits and behavior.
- [x] Root integration: inspect actual pinned LiteLLM schemas; exercise advertised key/team model/MCP fields against real upstream with synthetic licensing/model responses. Do not call unsupported fields supported. Browser tests verify new fields and progressive navigation with delayed inner responses.
- [x] Run backend formatting, full backend suite/coverage, frontend formatting/lint/typecheck/full unit tests/build/e2e/demo, docs/version/Helm/release-script checks and container build.
- [x] Review combined changes, fix meaningful findings with regression tests, commit/push focused branch, create/link PR and verify matching preview image. Keep release on hold.

## Review focus

- Advanced cannot set hidden bindings/spend/credentials, bypass organization policies or evade known Enterprise/positive-budget validation.
- Raw schema refs/defaults/errors cannot trigger external retrieval or disclose credentials.
- Missing upstream docs leaves familiar forms functional; unknown or malformed advanced values fail safely.
- Nested JSON and null clearing preserve untouched settings and reset when targets change.
- Initial organization loading performs no eager all-team reads or all-user usage calls; cached branches and slow errors do not block other navigation.

## Execution evidence

Three agents implemented the backend schemas, frontend Advanced controls and progressive organization independently. Independent review found silently dropped JSON Schema constraints; failure-first tests now cover those constraints and safe omission of unknown keywords. Live testing found LiteLLM 1.98 MCP team updates could discard the existing member-budget association; a dedicated helper preserves metadata and reuses the unchanged native member allowance without resending the reset duration. Unverifiable allowances fail before mutation. Team context decoration was moved intact to a small helper module so endpoint descriptions remain available and Python files stay below 400 lines.

Validation: 696 backend tests passed with 89.35% coverage; 115 frontend tests; 13 browser tests; 2 demo tests; live pinned LiteLLM contracts 3 passed/1 optional skip. Live Advanced policy integration verified key cap enforcement, key/team MCP settings, member defaults, rejection of zero/unknown fields, and preservation of the member budget across an MCP-only update. Formatting, lint, typecheck, production build/audit, docs/version checks, Helm/release checks and Docker build passed. Genuine Enterprise licensing and external MCP tool calls were not tested. Publication follows this validated source commit; the official release remains on hold.
