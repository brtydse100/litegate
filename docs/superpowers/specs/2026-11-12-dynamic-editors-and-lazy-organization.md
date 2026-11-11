# Dynamic policy editors and progressive organization loading

The user approved familiar key/team controls plus newly discovered fields under Advanced, the Python jsonschema dependency, and thorough parallel implementation/testing. The official release stays on hold.

## Dynamic fields

Read the connected LiteLLM's OpenAPI request schemas for key updates, team creation and team updates. Cache bounded schema data in process; expose only sanitized editable schema fields through an administrator-only endpoint. Resolve local references with bounded expansion and never retrieve remote references. Fixed identifiers, owner/membership bindings, spend counters, credentials and read-only/write-only fields remain controlled by their dedicated workflows.

Advanced opens on demand. Generate scalar/enum controls and JSON editors for complex values, with explicit opt-in edits and supported null clearing. Preserve familiar controls and their validations; avoid duplicate field submissions. Validate advanced changes server-side against the actual discovered schema, then apply existing Enterprise and hierarchy protections to the merged payload. Keep field-name-only audits, bounded concurrency and rate limits. Missing/disabled upstream OpenAPI affects Advanced only, not existing forms. Preserve current static fallback behavior.

The user selected this hybrid over fully generated forms. jsonschema is approved because nested references/constraints/unions should not be reimplemented ad hoc. No new service or persistent state is introduced. Tests must exercise advertised per-model budget and MCP fields, newly added schema fields, invalid/unknown fields, offline discovery and security boundaries. Unsupported upstream features must be reported honestly rather than invented.

## Lazy organization

The current overview waits for team_info on every configured node; initial usage and users also start for the entire organization. Replace the page's initial path with lightweight root metadata only. Expand/select a root to fetch its direct children and selected-team details. Repeat at each level; cache revisits. Defer usage/users until explicit group or All-groups selection, with independent loading/errors and accurate selected-branch aggregates. Do not describe the team's own spend as a whole-subtree aggregate. Keep legacy overview endpoints compatible.

The user reaffirmed progressive child loading after discussing lightweight whole-tree metadata as an alternative. Regression tests must demonstrate that slow/unrequested descendants do not delay initial rendering and that only relevant LiteLLM reads occur.

## Delivery

Use the existing isolated worktree on a new branch based on main. Agents own backend schemas, frontend Advanced controls, and lazy organization independently; root owns shared API/types, demo adapter, docs, integration and final validation. Preserve original checkout changes. Open a new focused PR after validation; publish its immutable matching preview image. Do not merge or release without the user's next direction.
