# Email organization mapping design

Status: original design and identity revision approved by the user.

## Approved identity revision following contract review

This section supersedes conflicting retirement, existing-email handling, and
readiness wording below. The hierarchy and configuration examples are unchanged.

1. Never delete users or transfer key ownership. When an authenticated legacy
   subject account takes precedence, retain any feature-owned reservation and
   mark it superseded only in LiteGate bookkeeping. Do not select or update that
   reservation again. It remains visible in LiteLLM and may count toward user
   limits; its memberships, keys, budgets, and history remain untouched. This
   bookkeeping status does not disable its LiteLLM account or credentials.
2. Email lookup identifies candidates, not ownership. Scan all relevant result
   pages and compare normalized exact emails locally. One ordinary account without
   proven identity remains pending until SSO login proves that its user ID is the
   authenticated legacy subject. Make no remote changes for it while pending.
   Reject known local/admin email-only conflicts, unrelated ambiguous matches,
   and conflicting bindings. Established administrative SSO identities keep their
   existing behavior; email alone must never establish identity.
3. Permit explicitly recorded pending identity confirmations during startup so
   their owners can log in. Report pending separately from provisioned users.
   Configuration errors, incomplete lookups, ownership conflicts, failed remote
   writes, and transport failures still fail the startup provisioning pass.
4. Scope bindings to provider authority and subject. Persist reservation intent
   and an ownership token before remote creation. Recover interrupted operations
   by exact reserved ID and matching remote ownership evidence. Persist canonical
   identity before memberships or session issuance; established bindings never
   silently switch accounts. Keep bindings when mapping is removed, so previously
   provisioned users retain their canonical identity and keys.
5. Acceptance requires exactly one selected canonical LiteLLM ID for each bound
   identity, rather than exactly one remote user record. Recorded superseded
   reservations are expected retained records, never recreated on restart.

The pinned `/user/delete` implementation deletes keys without an atomic keyless
condition. `/user/list` uses a paginated substring email filter; `/user/new` can
reject duplicate emails. These contracts require the above revision. Verify
creation metadata/ownership round trips, duplicate handling, and memberships
against the pinned live service before claiming integration validation. Docker
daemon availability is currently blocking those live checks.

Source: [pinned LiteLLM internal user endpoints](https://github.com/BerriAI/litellm/blob/d8f71d7bdbd7c9873d98293f83d64c6db72847e6/litellm/proxy/management_endpoints/internal_user_endpoints.py).

## Intent and constraints

Support companies whose SSO group claims are outdated. Deployers assign email
addresses to configured groups, and LiteGate adds membership in their ancestors.
Keep configuration readable, changes small, existing SSO group mappings intact,
and existing automatic key migration working. No new dependency, service, UI,
local password, or automatically generated key is needed.

The user selected email matching and inline member lists. Existing working-tree
changes, particularly key migration and deployment documentation, are user work.
Do not commit, push, or overwrite them.

## Approaches

Use a flat `groups` object with optional `parent`, `members`, and required
`team_id`. This was the recommended structure discussed with the user. Nested
`children` expresses the tree visually but makes deep Helm edits harder. A
separate email-to-groups object separates related data and adds configuration
indirection. Neither alternative is needed.

## Configuration contract

Integration ruling after fetching current `main` (v2.14): the already-shipped
`organizationHierarchy` budget/key policy remains authoritative and its
reconciliation is preserved. Reject overlapping managed team IDs before new
provisioning writes. For a user managed by both configurations, the existing
budget hierarchy chooses the primary team and key allowance. Reject canonical
identity changes that would silently discard an explicit legacy hierarchy path.
This is a compatibility constraint; it does not replace the new mapping schema.

- Backend settings: `organization_mapping` (default empty object) and
  `organization_mapping_file` (default empty string).
- Helm values: `config.organizationMapping` and `config.organizationMappingFile`.
- Inline mapping and file content have exactly the same `groups` schema.
- Configure one nonempty source only; reject conflicting sources rather than
  silently merging. An empty inline mapping does not conflict with a file.
- JSON files are UTF-8; relative paths resolve against the backend directory,
  matching the existing deployment's `/app/backend` layout.
- Groups have one parent at most. Root groups omit `parent`; `members` defaults
  to an empty list. Group names identify configuration nodes, not SSO claims.
- Each group references an existing LiteLLM team. Do not create teams, budgets,
  or a new LiteLLM organization entity.
- Trim and case-fold email addresses, deduplicate memberships, and reject invalid
  addresses, unknown fields, blank team IDs, repeated team IDs, missing parents,
  self-parenting, cycles, malformed JSON, and unreadable configured files.
- No configuration means existing behavior remains unchanged.

## Membership and primary team

Add direct email assignments and all ancestors. Never infer children or siblings.
Also expand ancestors of existing SSO-mapped teams that appear in this hierarchy.
Keep unlisted SSO-mapped teams and the existing default-team behavior.

Preserve existing SSO group mapping order and its primary team when matched.
Otherwise use the deepest directly email-assigned group as primary, breaking
equal-depth ties by configuration declaration order. Append remaining direct
teams and ancestors deterministically, deduplicated; append the existing default
team last when absent. Inherited ancestors never replace a direct primary team.
The mapping-required option accepts a match from either mapping source; the
default team alone continues not to satisfy it.

Reuse additive membership synchronization: removal from configuration does not
revoke existing LiteLLM membership. This first version is provisioning, not an
authoritative deprovisioning system. It does not grant administrator roles.

## Provisioning and identity proposal

At startup, validate configuration and resolve referenced teams before writes.
Provision configured emails and their memberships with `auto_create_key=False`.
Perform bounded work and report failures without logging secrets. No watcher:
file edits require restart, inline Helm edits require rollout. A failed startup
provisioning pass must not report readiness as successful; restart retries must
be idempotent. Unconfigured deployments retain their current readiness behavior.

Email is known before login but the provider's subject ID is not. Proposed
implementation: a small provisioning/binding table in the existing SQLite file,
created automatically with `CREATE TABLE IF NOT EXISTS`. It records feature-owned
reserved users and binds a provider identity to its canonical LiteLLM user ID.
This is necessary identity bookkeeping, not a second source of team membership.
It adds no infrastructure and fits the architecture's single-replica model.

Existing SSO subject-based user IDs take precedence and retain keys and history.
For a first-time user, reserve a namespaced deterministic ID from provider and
normalized email, then bind the authenticated provider subject on first login.
Check existing LiteLLM accounts before reserving users; never adopt a local or
administrative account merely because its email matches. Ambiguous account
matches must stop provisioning for that email with an actionable error.
Never merge existing accounts or transfer key ownership by email alone.
If an old subject-based account is discovered at login after reservation, keep
the old account, synchronize its memberships, and retire only the feature-owned
reservation after proving it is keyless and safe to remove. Persist the canonical
binding so restarts do not recreate that reservation.

Trust email only from the configured authenticated SSO flow; reject explicitly
unverified email for this feature. Providers omitting `email_verified` retain the
existing trusted-provider behavior. A reservation already bound to a different
provider subject cannot be claimed through email reuse. Keep OIDC validation,
generic SSO authentication, local authentication, and administrative role rules.

Use the canonical user ID for sessions and the existing automatic key migration.
Migration still runs at login and creates no keys. Existing sessions remain valid.

## Delivery and validation

Add focused modules for configuration resolution, identity bookkeeping, and
provisioning rather than expanding already-large files or refactoring unrelated
code. Keep new Python files below 400 lines. Document Docker read-only file
mounts, Helm inline values, existing ConfigMap file mounts, additive semantics,
primary-team ordering, identity binding, and restart requirements.

Verify LiteLLM lookup and safe reservation retirement against the repository's
pinned integration service before implementing these calls. The current service
wrapper does not yet provide these contracts; mocks alone are insufficient.
If the pinned service cannot support this identity proposal, revise this part
of the design for approval rather than substitute a global email-based user ID.

Acceptance: three-level inheritance, combined old/new mappings, preserved primary
teams and key migration, no keys at provisioning, one canonical account after
first login, repeatable startup/login, automatic SQLite initialization, secure
handling of identity conflicts, and equivalent Docker/Helm configuration.
