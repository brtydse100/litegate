# Changelog

All notable changes to LiteGate are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Redesigned the administrator bulk-key picker with searchable key cards, persistent cross-page selection, select-visible and clear-all actions, clearer key ownership and spend details, exact target counts, and a responsive mobile layout.
- Manual key-ID entry now lives under an advanced option, and successful bulk updates clear their targets to reduce accidental repeat operations.

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

[Unreleased]: https://github.com/brtydse100/litegate/compare/v2.4.0...HEAD
[2.4.0]: https://github.com/brtydse100/litegate/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/brtydse100/litegate/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/brtydse100/litegate/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/brtydse100/litegate/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/brtydse100/litegate/releases/tag/v2.0.0
