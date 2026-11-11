# Discovered key and team settings

The key and team editors keep their familiar controls. **Advanced settings**
discovers additional fields from the LiteLLM installation configured by
`LITELLM_URL`. LiteGate reads that installation's `/openapi.json` request schemas
for `/key/update`, `/team/new`, and `/team/update`; it does not infer editability
from an existing key or team's response fields.

## Using Advanced settings

1. Select a key or open a team editor, then expand **Advanced settings**.
2. Enable **Edit <field>** for each setting you intend to change.
3. Enter the value using the generated number, text, boolean, enum, or JSON control.
4. Submit the existing form. Untouched Advanced fields are not sent.

JSON values replace the complete field. Where the upstream schema permits null,
**Clear <field>** sends an explicit null; LiteLLM defines that field's clearing
behavior. Disabling **Edit** leaves the setting unchanged. Changing the selected
keys or reopening a different team discards drafts intended for the old target.
Saved values are prefilled when they are available in the returned record or its
metadata. Expanded response objects are projected onto editable schema properties;
internal IDs and unrelated metadata are not copied into the form. Some LiteLLM
settings live in associated records instead of the returned field; those values
must be entered explicitly when editing, while untouched settings stay preserved.

Examples of fields advertised by the pinned LiteLLM 1.98 integration instance:

- Keys: `max_parallel_requests`, `model_rpm_limit`, `mcp_rpm_limit`, and
  `object_permission`, including MCP server/tool permissions.
- Teams: `team_member_budget`, `team_member_budget_duration`, member RPM/TPM
  defaults, `mcp_rpm_limit`, and `object_permission`.
- Keys also advertise `model_max_budget`; LiteGate keeps its familiar dedicated
  per-model budget control, positive-amount validation, and
  `LITELLM_ENTERPRISE_ENABLED` requirement.

That version does **not** advertise a per-model team-member budget in its member
update schema. LiteGate does not invent support for unadvertised features. New
fields with supported schemas appear after schema cache refresh without a matching
LiteGate field definition. Changed endpoint contracts, licensing rules, and new
semantics can still require compatibility work.

## Discovery, validation and availability

Discovery is administrator-only and starts when Advanced opens. Backend results
are cached in process for five minutes (30 seconds for failures); the frontend
also caches discoveries for five minutes. No database or new service is involved.
The approved Python `jsonschema` dependency validates nested settings server-side.
The browser checks syntax and common types/bounds; the backend and LiteLLM remain
authoritative for complete constraints and cross-field business rules.

If LiteLLM's OpenAPI endpoint is disabled or unavailable, Advanced shows a retry
control and familiar fields continue to work. Advanced writes fail safely until a
usable schema is available. Some complex/unknown schema constructs are omitted
instead of exposing a field with weakened validation. Only local schema references
are resolved, with size/depth limits; remote references and redirects are not fetched.

Schema discovery does not prove Enterprise entitlement. LiteLLM still validates
its license and rejects unsupported features. The existing LiteGate Enterprise
flag continues to gate known per-model budget writes, including API writes.

## Policy boundaries

Only administrator portal sessions and the installation management credential can
use discovery and Advanced updates. Ordinary users and LiteLLM-key identities do
not gain administrative capabilities. Existing CSRF, cooldown, audit and bounded
bulk-update behavior remains in force.

Identifiers, ownership/membership bindings, spend counters, secret-bearing fields,
opaque authentication/routing configuration, and credential-rotation fields stay
with their dedicated workflows. They are not generic editable fields. Read-only
and write-only schema properties and schema defaults are excluded. Duplicate core
and Advanced fields are rejected rather than choosing one silently.

Organization-managed allowances remain protected, including dynamically discovered
budget-related settings. Separate per-model limits can restrict a key without
widening its inherited overall allowance. Editing unrelated MCP settings preserves
existing team metadata and member-budget associations; LiteGate reads selected-team
details first and fails before mutation if it cannot preserve an existing allowance.
Audit events contain the names of changed settings, never their submitted values.

The public demo uses a synthetic schema catalog and synthetic records only. It
never connects to a live LiteLLM installation.
