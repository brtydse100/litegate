# Per-model key budgets

Approved scope: administrators can set a model's USD allowance and independent reset period (for example, Opus $25 every 2h) on selected existing keys. Model spend still counts toward the overall key budget, and both limits apply.

## Approaches

The user selected a manual `LITELLM_ENTERPRISE_ENABLED` environment flag over automatic license detection. Default false; hide the editor and reject API writes of per-model budgets while disabled. The flag declares operator intent, not a verified license. LiteLLM remains responsible for enforcement and license validation.

## Design

Use LiteLLM's `model_max_budget` mapping of model names to `budget_limit` and `time_period`. Provide an explicit replacement editor with model/amount/period rows, saved values where available, and an explicit way to clear limits. Unedited budgets stay untouched. Explain replacement semantics when editing multiple keys. Validate nonnegative finite amounts, nonempty unique model names, and positive duration strings in seconds, minutes, hours or days. Preserve admin authorization, rate limits, audit records and per-key failures.

Remove nested scrolling from the key list and model chooser on Key policies. Memoize selection membership and selection identity to avoid quadratic searches and repeated sorting while typing. Preserve pagination and selection reset behavior.

Update environment/YAML/Helm configuration examples, API contracts and operator/user guides. No dependencies or persistent state. Work from current main in a separate worktree; preserve the original checkout. Open a PR without merging.
