# Per-model Key Budgets Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement these tasks in this session.

**Goal:** Add optional Enterprise per-model key budgets and make the key policy editor responsive with one page scrollbar.

**Architecture:** Default-off operator flag exposed in portal configuration and enforced by the bulk API. Forward validated native LiteLLM budget settings; do not implement budget accounting in LiteGate.

**Tech Stack:** FastAPI/Pydantic, React/TypeScript, pytest, Vitest; existing dependencies only.

**Spec:** `docs/superpowers/specs/2026-11-10-per-model-key-budgets-design.md`

## Global Constraints

- Preserve authorization, CSRF, rate limits, audit and bounded concurrency.
- Keep Python files under 400 lines and preserve unrelated user work.
- Default `LITELLM_ENTERPRISE_ENABLED=false`; no automatic license probing.

## Review Focus

- Disabled flag rejects attempted API writes, including clearing budgets.
- Invalid/duplicate model names, nonfinite or negative amounts, and zero or malformed periods cannot reach LiteLLM.
- Zero-dollar model budgets are rejected by the editor and HTTP API; positive fractional amounts remain valid.
- Replacing limits does not change the overall key budget or submit untouched values.
- Changing selection drops drafts intended for earlier keys.
- Cross-page selection and retries preserve existing behavior with large selections.

## Tasks

### 1. Backend contract and feature flag

- [x] Add failing tests in `backend/tests/test_model_budgets.py` for configuration default/environment parsing, portal flag, schema validation, authorization, disabled writes and native forwarding.
- [x] Run `python -m pytest tests/test_model_budgets.py -q`; expect missing feature failures.
- [x] Add `litellm_enterprise_enabled` in `config.py`, a focused model budget schema in `models.py`, the portal flag in `main.py`, and the admin API gate in `routers/api_v1.py`.
- [x] Run the backend suite; expect all tests passing.

### 2. Frontend editor and responsiveness

- [x] Add failing component tests for flag visibility, $25/2h payload, saved values, clearing and invalid input, and selection resets.
- [x] Add a focused `ModelBudgetEditor.tsx`, wire the flag through Home/AdminKeys/BulkKeyEditor, and extend API types.
- [x] Memoize selection membership and identity; remove nested list scrolling on Key policies while preserving other screens' layout.
- [x] Run `npm test`; expect all tests passing, including cross-page selection and retry coverage.

### 3. Documentation and PR

- [x] Synchronize `.env.example`, Compose YAML, Helm values/configmap/schema, `docs/configuration.md`, `docs/features.md`, and `API.md` with the flag and native budget contract.
- [x] Run backend formatting, frontend formatting/lint/typecheck/tests/build, docs/version checks, Helm lint and Docker build where tooling is usable.
- [x] Review the diff, commit and push only this branch's work, create and link the PR. Prepare the immutable preview image required by current repository instructions. Do not merge.

## Execution notes

The independent review found that regeneration would drop model limits or reset their usage windows. A regression test failed before adding a pre-mutation HTTP 409 guard in organization_sync.rotate_key. Both flag states are covered. Existing keys with these budgets require administrator-assisted rotation in LiteLLM.

Validation: backend suite and coverage gate; frontend unit tests, lint, formatting, typecheck, production build, production dependency audit; browser suite and demo suite; documentation/version checks; Helm lint and flag rendering. The local Docker daemon is unavailable; the preview publication workflow builds and verifies the image remotely.
