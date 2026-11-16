# LiteGate — PR #49 (Unreleased)

Draft notes for [PR #49](https://github.com/brtydse100/litegate/pull/49).
The stable version and release artifacts will be assigned after merge.

## Highlights

- **Organization migration:** Adopt existing users into `organizationHierarchy`
  without replacing IDs, credentials or spend. Apply configured policies before
  finalizing budgets; interrupted reconciliation retries without duplicate users.
- **Key safety:** Preserve rotation restrictions and expiration, detect source
  policy changes, and serialize administrator mutations with rotation. Restrictive
  legacy team policies require review before migration.
- **Security:** Reserve the bootstrap username, distinguish bootstrap sessions,
  audit legacy account routes, and clear private browser caches between accounts.
- **Portal:** Refresh migration status automatically, add manual refresh/retries,
  show actual known key restrictions, and improve password-reset errors, keyboard
  focus and mobile sign-out accessibility.
- **Release notes:** Compact Highlights and upgrade bullets replace long summaries.

## Release Artifacts

| Artifact | Get it |
| --- | --- |
| Preview image | [Verified preview and Docker pull command](https://github.com/brtydse100/litegate/pull/49) |
| Live demo | [Current demo](https://brtydse100.github.io/litegate/) |
| Migration guide | [Implementation documentation](https://github.com/brtydse100/litegate/blob/8c18314dd87fc76ef441b07ee0c4978c21f7c2a0/docs/organization.md#budgets) |
| Source | [PR changes](https://github.com/brtydse100/litegate/pull/49/files) |
| License | [Current MIT license](https://github.com/brtydse100/litegate/blob/main/LICENSE) |

## Upgrade Notes

- **Breaking:** Permanent key deletion is administrator-only. Owners replace
  credentials through spend-preserving rotation.
- Preserve SQLite and the existing key-storage setting. Review unresolved
  discovery conflicts and restrictive source-team policies in Organization.
- The bootstrap username is reserved case-insensitively; conflicting legacy
  sessions must sign in again. Database accounts need a different username.
- Keys with model budgets or additional budget windows require rotation by an
  administrator. Migration does not guess ambiguous identities or discard
  restrictions. No new dependency, service or spend ledger is introduced.

**Changes:** [#49](https://github.com/brtydse100/litegate/pull/49) by @brtydse100.

**Full Changelog**: [Changes since v2.18.0](https://github.com/brtydse100/litegate/compare/v2.18.0...fix/hierarchy-migration-and-review)

## Contributors

Thanks to @brtydse100.
