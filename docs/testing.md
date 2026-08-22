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
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=70

cd ../frontend
npm test
npm run test:e2e
npm run build
```

CI also validates dependency audits, Markdown links, version alignment,
Compose/Helm configuration, and the production Docker build. Backend line
coverage may increase over time, but CI prevents it from falling below 70%.
