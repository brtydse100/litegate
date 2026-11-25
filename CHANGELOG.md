# Changelog

All notable changes to LiteGate are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.23.2] - 2026-11-25

### Security

- People are provisioned in LiteLLM with the view-only `internal_user_viewer`
  role. Existing people with the plain `internal_user` role are switched at
  sign-in and once at startup (`litellm.user_role_restricted`), so their keys
  can no longer create unlimited keys outside LiteGate. Administrators and other
  roles are unchanged. A new guide shows the matching LiteLLM
  `key_generation_settings`.

## [2.23.1] - 2026-11-24

### Added

- The browser tab shows the LiteGate mark as its icon, or the configured
  `logo_url` when one is set.

### Changed

- A configured logo now fills the same rounded square tile as the default mark
  in the sidebar and on the sign-in page, instead of a white framed pill. Wider
  images are cropped to the square.

## [2.23.0] - 2026-11-24

### Added

- Restructuring the organization hierarchy reuses an existing LiteLLM team
  with the same name instead of creating a duplicate, when the match is
  unambiguous. Reuses and skipped reuses are audited
  (`organization.team_adopted`, `organization.team_adoption_skipped`).

### Changed

- `organization_cleanup_enabled` now cleans up instead of only auditing: people
  who moved leave their old managed teams, and removed teams that LiteGate
  created or reused are deleted once empty (`organization.membership_removed`,
  `organization.team_deleted`).
- Key search reads LiteLLM pages concurrently and briefly reuses the result;
  organization pages share one resolved member list; members already in sync
  skip the background sync; a budget change applies in the background while
  sign-ins wait briefly for it.
- Pages show loading placeholders, admin pages load on first visit, returning
  to the tab no longer reloads every page, and local accounts are paged.

## [2.22.2] - 2026-11-24

### Fixed

- The container image builds the frontend once on the build machine's own
  platform, so arm64 images no longer install frontend packages under
  emulation. Publishing is faster and no longer stalls at that step. Image
  contents are unchanged.

## [2.22.1] - 2026-11-24

### Changed

- **Audit log** is its own administrator page (`/audit`) with its own Refresh;
  **Status** shows only dependency readiness. Older `/status#audit` links open
  Audit log.
- The README and demo screenshots show the v2.22.0 redesign.

## [2.22.0] - 2026-11-23

### Added

- The Organization page can combine several departments at once, with an
  **All** choice. Cards, Needs attention, the spend split, the group table and
  the usage report cover the selection. `GET /api/v1/organization/users` and
  `/usage` accept a repeated `node` parameter (up to 50 groups, each
  scope-checked), and each `by_group` usage entry gains a `daily` array.
- The usage report shows Spend history, Requests history, Tokens by group and
  Spend by model as small charts with exact values on hover, tap or arrow keys,
  and it can be closed.
- Team owners get the administrator-style sidebar and Organization page for
  their own teams, a Team budget card, and in-place allowances in a People list.
  The demo adds an **Owner** role with a team of people and a team of teams.
- A breadcrumb shows the open group's path on the Organization page, and the
  Keys list filters by All, Active or Blocked with chips.

### Changed

- The portal follows Apple's Human Interface Guidelines: the system font, one
  blue accent, a light sidebar, large page titles, segmented controls and
  flatter grouped sections in light and dark themes. The IBM Plex font packages
  are removed.
- LiteGate has a new default mark, an arched gateway with a key slot, on the
  sign-in page, sidebar and top bar. A configured `logo_url` still replaces it.
- Anyone with administrator or team-owner access keeps the sidebar on My key
  and Analytics; ordinary users keep the top bar without an Admin link.

### Fixed

- In the department picker, clicking a team after **All** now shows just that
  team instead of switching it off.
- The usage report can be closed again, and level names pluralise correctly.

## [2.21.0] - 2026-11-20

### Changed

- My key, Organization, Teams, Keys, People, Status, Analytics and Sign in are
  redesigned with one calm design in light and dark themes. My key leads with
  what is left to spend, the refill date and whether spend is on track; the
  Organization page adds a spend split, a "Needs attention" list and an edit
  panel for each group. Layouts work from phones to wide screens, with keyboard
  and screen-reader improvements.
- The Organization page reads team status and member spend from two shared
  LiteLLM listings, each reused for a minute, instead of one request per group
  or member. Failed listings fall back to per-item reads.
- The organization sweep runs every `ORGANIZATION_SYNC_INTERVAL_SECONDS`
  (default 900, range 60 to 86400) instead of every minute. Budget and per-user
  limit edits wake it within about a minute, and failed passes retry from a
  minute with backoff.
- The README and demo media show the redesigned interface; the walkthrough
  video and drawings of the previous interface are removed.
- Large organizations with enforced budgets: a budget update now locks and
  re-reads only the groups it affects, so sign-ins and key replacements in
  different groups no longer wait for each other or for the background
  synchronization. Returning members sign in without any budget work, and the
  synchronization makes about a third of the LiteLLM requests.
- Organization usage reads LiteLLM's per-team activity (one request per 50
  teams) instead of one request per member, and the overview reuses team status
  for a minute. Reports support up to 5000 members.
- `KEY_ROTATION_SETTLE_SECONDS` (default 12) sets how long an enforced key is
  paused during regeneration.

### Added

- `SETUP_GUIDE_URL` adds a **Setup guide** link to My key for your own key
  usage instructions; blank hides it. The link no longer opens the API
  reference, which administrators find in their account menu.
- System administrators can set a group's per-user limit on Budget planning or
  in a configuration-managed team's Teams dialog, overriding the configured
  `perUser`; clearing it restores the configured value.

### Fixed

- The nightly browser run no longer runs the real-SSO tests without their
  Keycloak and LiteLLM services.
- OIDC sign-in no longer fails with a server error when the identity
  provider's clock runs slightly ahead of LiteGate's; ID-token times tolerate
  10 seconds of clock difference.

## [2.20.3] - 2026-11-18

### Fixed

- Members with enforced organization budgets can replace their own key again,
  including after moving to another group or a restart without persistent
  storage. The old key is paused while its spend settles, so the replacement
  carries the full spend; any failure keeps the old key.
- A member moved to another group with an existing key no longer blocks sign-in
  and budget updates for everyone; their key and spend move to the new group.

## [2.20.2] - 2026-11-18

### Fixed

- After a restart without persistent storage, the key page no longer reports a
  removed organization mapping: it shows a dismissible info notice to sign in
  again. Users moved to another group see where they were moved instead of a
  warning, and a key needing attention shows one message instead of two.
- The key page no longer offers **Regenerate key** when enforced organization
  budgets forbid replacing a managed key; it explains that the key keeps working.

### Changed

- Notifications and error banners can be closed with an **×** button. Form field
  validation is unchanged.
- Dark mode keeps light hover highlights readable, and a key without a saved
  copy now says the key still works instead of "Original key unavailable".

### Tests

- Real Keycloak/LiteLLM browser tests cover enforced budgets across restarts
  with and without persistence, and team administrators redistributing within
  their team's total without being able to change it.

## [2.20.1] - 2026-11-17

### Changed

- Display currency with two decimal places across spend, analytics, charts and
  allocation summaries, preserving stored amounts and precise numeric edits.
- Clarify assigned team totals as read-only for delegated team administrators;
  distinguish child allocations and retain backend authority checks, with direct
  API regressions for redistribution within the parent's existing allowance.

## [2.20.0] - 2026-11-17

### Added

- Opt-in enforced equal budget splits (`HIERARCHICAL_BUDGETS_ENFORCED`): each
  group's `groupTotal` is divided equally among members who signed in or hold a
  key, recalculated when someone joins, with `perUser` as a ceiling and
  Budget planning overrides and envelopes applied to key caps.

### Fixed

- Collect current managed-key spend before pinning allocations; verify required
  cap decreases before permitting increases. Failed reads, decreases or group
  transfers retain existing controls instead of releasing unverified capacity.
- Refresh spend floors after restarts and period resets, including deficits with
  unchanged allocation totals. Register first-time provisioning before pinning;
  keep a disappearing membership from aborting other users' synchronization.
- Verify incomplete key source metadata through key-info before budget writes;
  distinguish missing team information from an explicitly unassigned key.

### Upgrade Notes

- Enforcement defaults off. Enabled managed accounts currently support one key:
  additional keys, overlapping rotation, deletion and manual spend resets are
  blocked until aggregate accounting can preserve their allowance safely.
- Enforced allocations remain eventual per-key caps with separate reset periods,
  not strict atomic group limits. Managed transfers require operator review;
  automatic removed-group deletion remains unavailable. See the
  [governance guide](docs/governance-and-analytics.md#enforced-equal-splits).

## [2.19.0] - 2026-11-17

### Added

- Personal analytics for all portal users, backed by hourly incremental SQLite
  snapshots with request/token/cost/model/daily totals, coverage, freshness,
  failure retention and owner-only access.
- License-independent scoped Organization delegation requiring both an explicit
  designation and group administration, with subtree-only report data.
- Read-only People directory for registered SSO and no-key identities, including
  installations with local password accounts disabled.
- Opt-in durable hierarchical budget proposals with child reservations, manual
  direct-user overrides, equal automatic allocations and revision conflict checks.
  Activation is unavailable; proposals do not apply new inference limits.
- Ownership-backed, opt-in assessment and audit for removed organization groups;
  automatic deletion remains unavailable without atomic upstream safeguards.
- Real Keycloak SSO fixtures and CI coverage for identity, group changes,
  original-key retention, scoped access and account isolation.

### Changed

- Initialize shared SQLite state transactionally at startup using versioned
  migrations and bounded locking; preserve existing users, key copies and SSO
  bindings without runtime schema creation.
- Show complete, wrapping, copyable email addresses across user and team views.
- Return safe field-level Advanced policy errors without weakening validation.
- Document persistent storage for SSO-only Helm and Docker upgrades.
- Use concise Highlights-first release notes with compact artifact links and
  upgrade warnings, including reformatted historical notes.
- Restrict permanent key deletion to administrators; owners retain
  spend-preserving rotation. Reserve the bootstrap username case-insensitively.

### Fixed

- Adopt existing accounts into configured organization hierarchies while
  preserving IDs, credentials, spend, key restrictions and retry safety.
- Preserve rotation expiration and source policies; serialize administrator key
  changes with rotation and require review of restrictive legacy-team policies.
- Clear private browser caches between accounts, distinguish bootstrap sessions
  and audit legacy account routes.
- Refresh organization migration status automatically and improve password-reset
  errors, keyboard focus and mobile sign-out accessibility.

## [2.18.0] - 2026-11-12

### Added

- Optional per-model key budgets with independent reset periods, governed by
  the default-off `LITELLM_ENTERPRISE_ENABLED` flag and an upstream Enterprise license.
- Discovered Advanced key/team settings from the installed LiteLLM OpenAPI,
  including supported MCP settings and team-member allowance defaults, with
  generated controls, explicit edits, bounded caching and schema validation.
- Lightweight organization children/detail endpoints and progressive branch
  loading with cached revisits and deferred users/usage requests.

### Changed

- Key policies use one page scrollbar and cache selection calculations while editing.
- Distinguish selected-team spend from subtree usage aggregates. Keep familiar
  policy controls available when schema discovery fails.
- Reject self-service regeneration for keys with model budgets to preserve
  their limits and usage windows; reject misleading zero-dollar model limits.

### Fixed

- Preserve existing member-budget associations and metadata during unrelated
  Advanced MCP team updates on LiteLLM versions with metadata-backed settings.
- Preserve supported nested schema constraints and omit unsupported fields
  instead of advertising weakened validation.

## [2.17.0] - 2026-11-08

### Added

- Independent runtime `login_text` and `my_key_text` settings with environment
  and Helm equivalents, and the existing shared logo on the login page.
- Docker/Compose organization hierarchy examples covering YAML, JSON environment
  input, file mounts, precedence, and restarts alongside Helm documentation.

### Changed

- Use one action after one-time key creation or regeneration: **Hide API key**
  replaces regeneration until the secret is hidden, then regeneration returns.

### Fixed

- Correct the truncated Node setup action SHA that prevented Nightly E2E from
  starting dependency installation and browser tests.

## [2.16.0] - 2026-11-06

### Added

- Optional positive `key_max_parallel_requests` default for newly created and
  regenerated keys, including organization-managed keys, with environment and
  Helm configuration support.

### Fixed

- Preserve the configured full Model Hub URL without appending a path. Existing
  base-only links should be updated to their desired complete destination.

## [2.15.4] - 2026-11-05

### Fixed

- Preserve original owned-key identifiers during metadata refresh so saved
  secrets remain discoverable; defer replacement advice during unresolved lookups.
- Await initial hierarchy reconciliation and discover existing accounts by exact
  ID or configured email without login, preserving keys and spend. Revalidate
  remote email assignments every pass without changing SSO ownership checks.

## [2.15.3] - 2026-11-05

### Fixed

- Display distinct sub-dollar and microdollar chart labels and scale usage bars
  to the actual maximum, including spend below one dollar.
- Read live owned-key spend for the homepage and verify carried spend after
  regeneration policy updates; retain original keys if LiteLLM cannot confirm
  the replacement counter.

## [2.15.2] - 2026-11-05

### Added

- Load the existing organization hierarchy from a UTF-8 JSON file at startup
  using `organization_hierarchy_file` / `ORGANIZATION_HIERARCHY_FILE`.
- Mount an existing ConfigMap hierarchy file through top-level Helm
  `organizationHierarchyFile`, with validation and rollout checksums.

## [2.15.1] - 2026-11-04

### Fixed

- Honor generic SSO email verification opt-out consistently through login.
- Resolve normalized SSO emails in existing hierarchy `userIds` with the same
  single-path membership and inherited budget policy as SSO groups.

### Changed

- Remove standalone organization mapping/file options. Migrate email assignments
  to hierarchy members' `userIds`. Provision actual subjects at first login
  without keys, remote email lookup at startup, or new reservations.
- Preserve 2.15.0 canonical bindings and ownership-proven legacy claims without
  deleting users or transferring keys. Persist SSO email/source for policy checks.

## [2.15.0] - 2026-11-03

### Added

- Email-based organization mapping from inline Helm/Compose configuration or a
  JSON file, with named levels, parent membership inheritance, and compatibility
  with the original flat mapping format. Existing SSO mappings and managed
  organization budget policies retain their precedence.
- Keyless provisioning before first SSO login, durable provider/subject identity
  binding, pending confirmation for existing accounts, and safe retention of
  superseded reservations. Membership synchronization remains additive.
- Per-PR immutable preview Git/image tags and verified publication guidance.

## [2.14.0] - 2026-10-26

### Changed

- Existing owned keys move into the configured primary or deepest organization
  team at login/reconciliation, including keys already in another team, while
  retaining secrets, spend, and old memberships. Managed allowance verification
  and ancestor-restriction safeguards remain in force.
- Personal key spend shows six decimal places, and rotation retains the normal
  key name with alias-safe replacement and failure recovery.
- Leaf organization groups show each member's selected-period spending.

### Documentation

- Highlight the requirement to upgrade the Helm chart and image together when
  enabling organization hierarchy.

## [2.13.0] - 2026-10-15

### Added

- Configurable organization hierarchy with up to eight levels, real lowest-team
  key ownership, inherited per-key allowances, ancestor usage tracking, and
  administrative reports. Helm and Compose support the same policy structure.
- Explicit administrator migration from duplicate personal/member budgets to a
  verified sole-key allowance, plus an administrator model-name catalog.
- Isolated LiteLLM/OpenRouter testing helpers with real requests and artificial
  local accounting prices for exercising budgets.

### Changed

- Key and team editors show current values, use model checkboxes and themed
  numeric controls, and reveal editing settings only after key selection.
- Personal keys use a shared compact green display, an accessible copy icon and
  a full-width Show/Hide control. Config-managed teams have a visible tag.

### Fixed

- Key rotation and budget migration share the owner lock, preserve recorded
  spend and finite individual allowances, and revoke unverifiable replacements.
- Valid roster-only LiteLLM members can migrate without a separate budget row;
  ownership and hierarchy governance are rechecked before removing user caps.
- Sub-cent spend remains visible in Teams, Organization and key policies.

## [2.12.2] - 2026-10-05

### Added

- Optional outgoing HTTPS certificate verification control through `ssl_verify`
  and Helm `config.sslVerify` for LiteLLM and all SSO requests.
- Optional generic SSO email verification control through
  `generic_require_verified_email` and Helm `config.genericRequireVerifiedEmail`.
  Both verification settings remain enabled by default.

### Fixed

- Helm rejects custom CA paths or keys without a ConfigMap or Secret source,
  instead of silently ignoring them. Examples explain how to load a local CA
  bundle and distinguish its source from the destination inside the pod.

## [2.12.1] - 2026-10-01

### Changed

- Helm deployment documentation includes a minimal values example and explains
  defaults, explicit disabling, list replacement, and upgrades without retaining
  removed overrides.
- The bundled Helm values reference includes name overrides, the optional
  management API credential, and the deprecated team-mapping alias.

## [2.12.0] - 2026-09-30

### Added

- Generic OAuth SSO authenticates through UserInfo with opaque access tokens,
  configurable identity fields, scopes, optional S256 PKCE, and body or HTTP
  Basic client authentication.
- Compose YAML and Helm `config:` settings accept `GENERIC_*` environment
  overrides while preserving existing administrator/team and OIDC rules.

### Changed

- Release notes share an Artifacts, What's Changed, Full Changelog, and
  Contributors format; `AGENTS.md` records the template and publication rules.

### Fixed

- OAuth HTTP Basic authentication form-encodes reserved characters in client
  credentials before constructing the header.
- Helm rendering regression checks tolerate an absent terminal newline while
  still verifying exact configuration values and Secret placement.

## [2.11.0] - 2026-09-30

### Added

- Optional SQLite API key storage lets owners and administrators reveal saved
  keys on demand, with current LiteLLM ownership checks and secret-free audits.
- Manual OIDC authorization, token, and JWKS endpoints support providers that
  need explicit configuration while retaining token and login-flow verification.
- SSO users can inherit an existing default LiteLLM team and, when explicitly
  enabled, the full LiteLLM `proxy_admin` role.
- Helm supports custom CA bundles and templated additional Kubernetes resources,
  including OpenShift Routes; its environment reference covers all settings.

### Changed

- Helm configuration groups related settings while preserving existing
  configuration and credential values.
- Release publication verifies the container image before creating the GitHub
  Release, validates official tags against `VERSION` and `main`, and restricts
  manual image tags and shared-alias promotion.

### Fixed

- SQLite cleanup failures after successful key revocation no longer cause
  regeneration to delete the working replacement; warnings exclude credentials.
- Legacy Helm `oidcRequireTeamMapping` and `managementApiKey` values continue to
  enforce their authentication behavior.
- OIDC tests no longer depend on an undeclared mocking package.

## [2.10.0] - 2026-09-24

### Added

- The Helm chart now accepts additional pod volumes and container volume mounts,
  including externally managed storage for `/app/backend/data`.
- Container publishing verifies that the release image completes a standard
  Docker pull, save, load, and inspection round trip.

### Fixed

- Release images no longer embed attestation manifests that can leave some
  Docker content stores unable to export a pulled multi-platform image.
- Transient authentication-configuration failures no longer silently hide the
  SSO login button; the login page retries and presents a recoverable error.

## [2.9.0] - 2026-08-26

### Added

- Audit-event retention is configurable and cleanup runs in bounded batches as
  new audit events are written.

### Fixed

- Public readiness responses no longer expose the configured LiteLLM target.

## [2.8.0] - 2026-08-25

### Fixed

- Preserved the legacy API response shape for key-spend resets.
- Recursively redact sensitive values from audit-event details.

## [2.7.0] - 2026-08-24

### Added

- Dashboard users can view the models available to their LiteLLM key.
- Administrators can reset spend for selected keys.

### Changed

- Local-user navigation can be configured, and non-administrators no longer see
  the administrator sidebar.
- Release notes now provide exhaustive, commit-traceable change lists.

## [2.6.1] - 2026-08-24

### Changed

- Made key regeneration and support actions full-width, higher-contrast
  controls so the portal's primary next steps are easier to identify and use
  across desktop and mobile layouts.
- Refreshed the public screenshots, SVG source, and demonstration video to
  match the updated action hierarchy.

## [2.6.0] - 2026-08-23

### Added

- A persisted light/dark theme toggle is available on both the sign-in screen
  and authenticated portal.
- The public browser-only demo can switch between administrator and ordinary
  user roles without credentials or a live LiteLLM deployment.
- Pull requests now run frontend linting, formatting, type checking, focused
  browser smoke coverage, and backend formatting alongside the existing test,
  audit, packaging, documentation, and version checks.
- A scheduled workflow runs the complete Playwright suite nightly, while the
  interactive GitHub Pages demo has its own deployment-time behavior test.
- An opt-in integration stack uses pinned LiteLLM and PostgreSQL images to
  verify live user, team, and virtual-key contracts through both the backend
  service layer and the browser-facing LiteGate API.

### Changed

- Redesigned the portal with the light, compact information hierarchy of the
  LiteLLM administrator interface, including a desktop sidebar, responsive
  mobile navigation, clearer key summaries, and consistent administration
  pages.
- Replaced the static public demonstration with the real frontend backed by a
  browser-only synthetic API, so key regeneration, teams, users, policies, and
  status views can be explored safely.
- Refreshed and compressed screenshots, SVGs, and the demonstration video for
  sharper documentation with substantially smaller downloads.
- Split fast browser smoke coverage from the complete nightly suite to keep
  pull-request feedback focused without losing broader regression coverage.

### Fixed

- The public demo no longer advertises unsupported SSO login.
- User provisioning now explicitly disables LiteLLM's automatic key creation,
  preventing an unrevealed initial secret from blocking self-service key setup.
- Team updates normalize LiteLLM's nested response shape so the API and portal
  receive the complete updated team record.

## [2.5.0] - 2026-08-22

### Added

- Authenticated Prometheus metrics, safe `X-Request-ID` propagation, and
  secret-free structured request logs improve production observability.
- Session secrets can be rotated without immediately invalidating existing
  sessions by configuring verification-only prior secrets.
- A maintenance command creates verified SQLite backups and requires an
  explicit confirmation while preserving a safety copy before restoration.
- Browser contracts now cover team creation/editing/deletion, safe member and
  key movement, and local-account administration.
- The backend CI coverage floor increased from 70% to 75% after public-route
  coverage expanded.
- Black-box HTTP contract tests now define session-cookie, logout, OIDC state/nonce, password-throttling, key-deletion, and administrator-boundary behavior through public routes.
- A testing-strategy guide records that behavior changes start with a failing contract, while implementation refactors must not rewrite those contracts.
- CI now measures backend coverage and rejects regressions below the initial 70% floor.
- Administrators can select every key in the installation from the bulk editor, not only keys visible on the current page. The explicit action fetches identifiers through bounded pagination and supports up to 5,000 keys.
- Global key search and team/blocked filters can scope both paginated results and the select-all operation.
- Administrator status and audit views expose dependency readiness and secret-safe management history.
- Dedicated liveness/readiness probes, frontend unit/browser tests, and pull-request CI cover backend, frontend, Helm, documentation, version alignment, and container builds.
- Tag-driven GitHub release automation publishes the matching checked-in release note.
- Password login now throttles repeated failures per client, and OIDC login binds state to an HttpOnly browser cookie and verifies the ID-token nonce.

### Changed

- Redesigned the administrator bulk-key picker with searchable key cards, persistent cross-page selection, select-visible and clear-all actions, clearer key ownership and spend details, exact target counts, and a responsive mobile layout.
- Manual key-ID entry now lives under an advanced option, and successful bulk updates clear their targets to reduce accidental repeat operations.
- Standardized the release-note pages and repaired the malformed published 2.4.0 release body.
- Reused a pooled LiteLLM HTTP client, made YAML configuration side-effect free, replaced the password-reset browser prompt with an accessible dialog, and consolidated production packaging on the all-in-one non-root image.
- Helm now enforces the supported single-replica SQLite/in-process state model and uses separate liveness/readiness probes.
- Local source-build Compose deployments now restart automatically after a host reboot, and the frontend clears SSO credentials from the URL immediately after reading them.
- Team dialogs now close consistently with Escape or a backdrop click and prevent background-page scrolling while open; the Status tab also flags weak deployment secrets or non-local HTTP configuration.
- Key deletion now sends credentials in the request body instead of the URL, preventing reverse-proxy access logs from capturing full virtual keys; cross-origin methods and headers are explicitly limited.
- A top-level recovery screen prevents an unexpected frontend render error from leaving administrators on a blank page.
- New SSO and password sessions use SameSite, HttpOnly cookies instead of browser-readable local storage; bearer authentication remains available for API clients and existing sessions.
- Cookie-authenticated mutations reject unapproved cross-site origins to retain CSRF protection after the session-storage change.
- The bundled Nginx proxy preserves the original host port, keeping origin checks correct on non-default development and production ports.

## [2.4.0] - 2026-08-20

### Added

- The portal now disables key, account, team, and bulk-edit mutation controls while the authenticated user has exhausted the server-side operation allowance, with a live retry countdown.
- Local-account mutations now use the same server-side allowance as key and team changes, preventing rapid repeated role, password, or enable/disable requests.

### Changed

- Key regeneration carries accumulated spend into the replacement key, preventing credential rotation from refreshing a per-key allowance.
- Replacement keys are created before old credentials are revoked, with rollback if old-key cleanup fails.

### Security

- The all-in-one container now runs as the dedicated unprivileged UID/GID `10001:10001`, drops Linux capabilities in Helm, prevents privilege escalation, and uses the runtime-default seccomp profile.
- Nginx listens on unprivileged container port `8080`; Docker Compose and the Helm Service continue exposing port `80`.

### Deployment

- Existing Docker volumes created by earlier root-running images may require a one-time ownership migration before upgrading.

## [2.3.0] - 2026-08-20

### Added

- An administrator-only, few-click workflow for viewing team members and moving a member to another LiteLLM team.
- An administrator API endpoint for moving a team member and their source-team keys.

### Security

- Member moves add the destination membership and verify scoped-key migration before removing the source membership, avoiding LiteLLM's source-member deletion side effect.
- The move requires explicit policy-change confirmation, is limited to 500 source-team keys, and is blocked for configuration-managed source teams.
- Normal users cannot view team members or move them in either the portal or API.

### Deployment

- The public container is published as `ghcr.io/brtydse100/litegate:2.3.0` and `:latest` after the release workflow completes.

## [2.2.0] - 2026-08-20

### Added

- An administrator-only Teams tab for paginated search, team creation, and one-click policy editing.
- Administrator API endpoints for listing, creating, updating, and deleting LiteLLM teams.

### Security

- Team deletion requires exact-ID confirmation in the portal and is blocked while a team is referenced by SSO mapping or the default key-team setting.
- Normal users cannot access team management in either the portal or API.

### Deployment

- Clarified Helm-specific SSO administrator-role and LiteLLM team-mapping values, and refreshed the deployment examples for the 2.1 release.
- The public container is published as `ghcr.io/brtydse100/litegate:2.2.0` and `:latest` after the release workflow completes.

## [2.1.0] - 2026-08-20

### Added

- Configuration-driven, case-insensitive SSO group mapping to existing LiteLLM teams, including one-to-many mappings and nested group claim paths.
- Optional fail-closed SSO access that requires users to match a configured LiteLLM team.

### Changed

- SSO login now additively synchronizes mapped team memberships and applies the first matched team to newly created or regenerated keys for LiteLLM team budget and model enforcement.
- Existing keys remain unchanged until regeneration or administrator update, and team membership removal remains an explicit LiteLLM administration action.

### Deployment

- The public `linux/amd64` container is available as `ghcr.io/brtydse100/litegate:2.1.0` and `:latest` with provenance metadata.

## [2.0.0] - 2026-08-20

### Added

- Persistent administrator-managed local accounts with `user` and `admin` roles, password resets, and enable/disable controls.
- Generic OpenID Connect login with administrator assignment by email or group, including nested group claim paths.
- Stable `/api/v1` automation endpoints for identity, key management, bulk key updates, and local-user administration.
- Optional `management_api_key` authentication for trusted administrator automation.
- Administrator-only, paginated bulk key editing for aliases, models, budgets, reset periods, rate limits, duration, and blocked state.
- Docker Compose and Helm deployment resources with persistent local-user storage.
- OpenAPI, Swagger UI, ReDoc, health, custom-logo, model-hub, and support-link integration.
- Product documentation and the LiteGate banner artwork.

### Changed

- The dashboard now renders spend and policy information from returned key records instead of downloading raw spend logs during normal page loads.
- Installation-wide key lists load only when an administrator opens the bulk editor and are paginated.
- Key creation, reveal, copy, regeneration, account management, and role descriptions have clearer interface guidance.
- Bulk key editing is restricted to administrators in both the interface and API.
- Bulk updates preserve omitted fields, use bounded concurrency, and report per-key failures.

### Security

- OIDC state is signed and time-limited, and ID tokens are verified for signature, issuer, audience, and expiry.
- Portal tokens returned from OIDC use a URL fragment to avoid server access-log exposure.
- Local passwords use salted PBKDF2-SHA256 hashes; unknown-user authentication performs a dummy hash check.
- Disabled local accounts and local role changes take effect on the next authenticated request.
- Key-changing operations are rate-limited, secret comparisons use constant-time checks where applicable, and the included Nginx configurations add browser security headers.

### Deployment

- LiteGate can be built as one container containing the React frontend, Nginx, and FastAPI backend.
- A public `linux/amd64` container package is available as `ghcr.io/brtydse100/litegate:2.0.0` and `:latest`; other architectures can build locally with the included Docker Compose configuration.

[Unreleased]: https://github.com/brtydse100/litegate/compare/v2.23.2...HEAD
[2.23.2]: https://github.com/brtydse100/litegate/compare/v2.23.1...v2.23.2
[2.23.1]: https://github.com/brtydse100/litegate/compare/v2.23.0...v2.23.1
[2.23.0]: https://github.com/brtydse100/litegate/compare/v2.22.2...v2.23.0
[2.22.2]: https://github.com/brtydse100/litegate/compare/v2.22.1...v2.22.2
[2.22.1]: https://github.com/brtydse100/litegate/compare/v2.22.0...v2.22.1
[2.22.0]: https://github.com/brtydse100/litegate/compare/v2.21.0...v2.22.0
[2.21.0]: https://github.com/brtydse100/litegate/compare/v2.20.3...v2.21.0
[2.20.3]: https://github.com/brtydse100/litegate/compare/v2.20.2...v2.20.3
[2.20.2]: https://github.com/brtydse100/litegate/compare/v2.20.1...v2.20.2
[2.20.1]: https://github.com/brtydse100/litegate/compare/v2.20.0...v2.20.1
[2.20.0]: https://github.com/brtydse100/litegate/compare/v2.19.0...v2.20.0
[2.19.0]: https://github.com/brtydse100/litegate/compare/v2.18.0...v2.19.0
[2.18.0]: https://github.com/brtydse100/litegate/compare/v2.17.0...v2.18.0
[2.17.0]: https://github.com/brtydse100/litegate/compare/v2.16.0...v2.17.0
[2.13.0]: https://github.com/brtydse100/litegate/compare/v2.12.2...v2.13.0
[2.12.0]: https://github.com/brtydse100/litegate/compare/v2.11.0...v2.12.0
[2.11.0]: https://github.com/brtydse100/litegate/compare/v2.10.0...v2.11.0
[2.10.0]: https://github.com/brtydse100/litegate/compare/v2.9.0...v2.10.0
[2.9.0]: https://github.com/brtydse100/litegate/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/brtydse100/litegate/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/brtydse100/litegate/compare/v2.6.1...v2.7.0
[2.6.1]: https://github.com/brtydse100/litegate/compare/v2.6.0...v2.6.1
[2.6.0]: https://github.com/brtydse100/litegate/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/brtydse100/litegate/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/brtydse100/litegate/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/brtydse100/litegate/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/brtydse100/litegate/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/brtydse100/litegate/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/brtydse100/litegate/releases/tag/v2.0.0
