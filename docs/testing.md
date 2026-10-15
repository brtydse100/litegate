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

The current budget management contract can be exercised against a disposable
LiteLLM instance with a database. Set `LITELLM_URL`, `LITELLM_MASTER_KEY`, and
`JWT_SECRET`, then run from `backend`:

```bash
RUN_LITELLM_INTEGRATION=1 RUN_LITELLM_ORGANIZATION_INTEGRATION=1 \
  python -m pytest tests/integration/test_litellm_live.py -v
```

This creates temporary test users, teams, and keys. It checks lowest-team ownership,
per-key budgets, unchanged spend/reset windows during allowance edits, and carried
spend during key replacement. Teams and keys are removed afterward; test users
remain for inspection. The pinned CI stack also runs this management contract;
it checks budget persistence and reset windows without requiring a license.
Enterprise request enforcement and analytics access still require validation on
a licensed deployment. Never run this against a production proxy.

## Manual local testing

With Docker Desktop running and the backend/frontend dependencies installed, run
from the repository root:

```powershell
python scripts/local_test.py start
python scripts/local_test.py providers
```

The first command starts the isolated Compose stack on `127.0.0.1:4000`, a real
LiteGate backend on port 8000, and the frontend on port 5189. It prints local
login credentials for `admin`, `alice`, `bob`, and `carol`. Generated credentials
and logs use ignored `.env.local-test*` paths. It preserves an existing
`backend/config.yaml`; otherwise it copies
[the manual hierarchy example](../deploy/docker-compose/config.local-test.yaml).
Saving that config reloads the backend; periodic reconciliation runs every 60
seconds. Do not commit the local config or use this stack with production data.
If setup stops after starting the backend, rerun `start`: it reuses the running
instance only after authenticating with this setup's saved management credential.
An instance with different credentials is rejected before any accounts are changed.

The second command prompts for an OpenRouter API key without echoing it (or reads
`OPENROUTER_API_KEY`). It registers `free-router` and up to two current `:free`
models from different model authors after checking their token prices are zero.
Provider credentials are stored by the local LiteLLM instance. Existing aliases
are preserved. OpenRouter account quotas and model availability still apply.
The credential is verified before any model is created. To replace an invalid
provider key while preserving model routes and prices, run
`python scripts/local_test_models.py refresh-key` and enter the new key locally.

Open <http://localhost:5189>, sign in as a test user, and create that user's key.
Then send a real request through LiteLLM:

```powershell
python scripts/local_test.py request --model free-router --count 3
```

The script prompts for the user's virtual key without echoing it, or reads
`LITEGATE_TEST_KEY`. It prints model responses and token usage. Try `free-1` and
`free-2` if registered. The example assigns Alice to Platform with a $5 key cap,
Bob directly to DevOps with $20, and Carol to Engineering with $50. Ancestor
targets track usage only. Parent counts remain visible in the Organization tree;
the lowest configured level hides its count.

Use **Show API key** on this real portal. Keys from the browser-only public demo
cannot authenticate to the local proxy. A native 401 indicates a virtual-key
problem; an OpenRouter 401 indicates a provider credential problem. The helper
distinguishes these without printing credentials. A key created before secret
storage was enabled may require regeneration; its original secret cannot be
recovered from LiteLLM's hash.

For faster budget testing, assign artificial local accounting rates to two real
free routes:

```powershell
python scripts/local_test_models.py pricing
python scripts/local_test.py request --model free-2 --max-tokens 16
python scripts/local_test.py request --model free-1 --max-tokens 16
```

`free-1` uses $0.10 per input/output token and `free-2` uses $0.0001 per token
in LiteLLM's local accounting. These are test rates, not OpenRouter charges;
the upstream routes remain free and requests use real providers. The pricing
command uses LiteLLM's OpenAI-compatible adapter with the exact OpenRouter API
endpoint for these two aliases. The native OpenRouter adapter prioritizes the
provider's zero-dollar cost over custom prices; the compatible adapter lets
LiteLLM calculate the artificial test rates. Existing credentials and underlying
free model IDs are preserved. Input tokens
also count, so a single expensive request can exceed Alice's $5 allowance.
Check the recorded spend and retry to test the next-request budget rejection.
The request helper prints **LiteLLM accounted cost** separately from OpenRouter's
zero `usage.cost`. Refresh the portal after sending requests to load updated spend.
`free-router` retains its default free pricing. Pricing setup verifies the saved
rates; successful inference and spend enforcement still require a valid provider
credential and available provider quota. The disposable management integration
tests above also cover controlled spend and budget transitions.
