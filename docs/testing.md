# Testing strategy

LiteGate tests are organized around observable behavior first. Internal unit
tests are useful for calculations and edge cases, but they do not replace the
public contracts that users and automation depend on.

## Test layers

1. **HTTP contract tests** call the ASGI application through real routes. They
   define authentication, authorization, cookie, CSRF, rate-limit, key, team,
   and compatibility behavior without calling router functions directly.
2. **Browser tests** assert navigation, role boundaries, cross-page selection,
   and compatibility with an older API response during rolling upgrades.
3. **Unit tests** cover deterministic helpers such as configuration mapping,
   spend carry-over, pagination normalization, and audit redaction.
4. **Container checks** prove the production image builds, runs unprivileged,
   reports readiness, and can reach its configured dependencies.

When behavior changes intentionally, update the contract first so the failing
test records the new requirement. Then change the implementation until it
passes. Refactoring private functions should not require contract changes.

## Commands

```bash
cd backend
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=75

cd ../frontend
npm test
npm run test:e2e:smoke
npm run build
```

The short Playwright smoke flow runs for pull requests. The complete browser
suite runs nightly and remains available locally with `npm run test:e2e`.

CI also validates dependency audits, Markdown links, version alignment,
Compose/Helm configuration, and the production Docker build. Backend line
coverage may increase over time, but CI prevents it from falling below 75%.

## Organization budgets

Hierarchy tests cover inheritance, conflicting mappings, administrative role
boundaries, synchronization ordering, and complete usage totals. The chart has
rendering tests in `scripts/test_organization_helm.py`; the public demo browser
flow checks group filtering, allowance overrides, charts, and user restrictions.

The current Enterprise budget contract can be exercised against a disposable
LiteLLM instance with a database. Set `LITELLM_URL`, `LITELLM_MASTER_KEY`, and
`JWT_SECRET`, then run from `backend`:

```bash
RUN_LITELLM_INTEGRATION=1 RUN_LITELLM_ORGANIZATION_INTEGRATION=1 \
  python -m pytest tests/integration/test_litellm_live.py -v
```

This creates temporary test users, teams, and keys. It checks applied member
budgets and verifies that key replacement and allowance changes preserve the
member's spend and reset window. Teams and keys are removed afterward; test users
remain for inspection. Use a current Enterprise deployment; the ordinary pinned
CI integration stack does not opt into this version-specific test or require a
license. Never run this against a production proxy.
