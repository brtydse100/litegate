# Authentication and security

LiteGate supports browser sessions through OpenID Connect or local accounts, and
API access through a portal JWT, LiteLLM virtual key, or management API key.

## Local accounts

Set `local_auth_username` and `local_auth_password` to enable the bootstrap
administrator. After signing in, an administrator can use the **Users** tab to
create persistent local accounts, assign `user` or `admin`, reset passwords, and
enable or disable accounts.

Local users are appropriate for:

- setup and recovery before SSO is ready;
- controlled break-glass administration;
- people outside the configured identity provider; and
- temporary access during an SSO outage or migration.

Local passwords are salted and hashed with PBKDF2-SHA256 using 310,000
iterations. The account database uses SQLite WAL mode. Docker Compose persists
it in the `litegate-data` volume; the Helm chart enables persistent storage by
default.

## OpenID Connect SSO

Register the following callback with the identity provider:

```text
https://litegate.example.com/api/auth/callback
```

Then configure the provider:

```yaml
oidc_issuer_url: "https://login.example.com/realms/company"
oidc_client_id: "litegate"
oidc_client_secret: "replace-me"
oidc_redirect_uri: "https://litegate.example.com/api/auth/callback"
oidc_scopes: "openid email profile"
```

Common issuer patterns:

| Provider | Issuer URL pattern |
| --- | --- |
| Google | `https://accounts.google.com` |
| Microsoft Entra ID | `https://login.microsoftonline.com/<tenant-id>/v2.0` |
| Okta | `https://<domain>.okta.com/oauth2/default` |
| Keycloak | `https://<host>/realms/<realm>` |

## Assigning administrators

SSO users receive administrator access when their email or group matches the
configured comma-separated values. Matching is case-insensitive.

```yaml
admin_emails: "owner@example.com,platform@example.com"
admin_groups: "Platform Admins,AI Operations"
oidc_groups_claim: "groups"
```

Nested token claims are supported with dot notation:

```yaml
admin_groups: "litegate-admins"
oidc_groups_claim: "realm_access.roles"
```

The provider must put the desired value directly in the ID token. Configure IDs
when the token emits group IDs. Group-overage references are not resolved by
LiteGate, so configure the provider to include the required group. Add a
provider-specific scope such as `groups` to `oidc_scopes` when necessary.

## Mapping SSO groups to LiteLLM teams

LiteGate can add an SSO user to existing LiteLLM teams at login and apply a
primary team to keys the user creates. This lets LiteLLM enforce the team's
models and budget without giving users access to the LiteLLM administrator UI.

Map each identity-provider group to one team ID or a list of team IDs:

```yaml
oidc_groups_claim: "groups"
oidc_group_team_mapping:
  Engineering: "team-engineering"
  AI-Platform:
    - "team-platform"
    - "team-shared-services"
oidc_require_team_mapping: false
```

Group matching is case-insensitive. `oidc_groups_claim` also accepts a dotted
path such as `realm_access.roles`. The mapped LiteLLM teams must already exist;
LiteGate does not create teams or define their budgets.

At each successful SSO login, LiteGate additively syncs membership for every
matched team. If more than one group matches, the first team in configuration
order becomes the user's primary team. That team is applied to newly created or
regenerated keys so LiteLLM can enforce its model and budget policy. Existing
keys are not silently reassigned: regenerate the key or have an administrator
update it.

LiteGate does not automatically remove team memberships when an SSO group is
removed, because removing a LiteLLM team member can also delete that member's
team keys. Remove stale membership deliberately in LiteLLM after reviewing its
keys. A mapping or membership error fails the login instead of allowing a user
to continue without the intended team controls.

Set `oidc_require_team_mapping: true` to deny SSO login when none of the user's
groups has a configured team. Leave it `false` while rolling the feature out or
when unmapped SSO users should retain the global key defaults.

## API credentials

| Credential | Header | Authorization |
| --- | --- | --- |
| Browser session | HttpOnly `litegate_session` cookie (automatic) | Personal operations for users; admin operations only when the session role is `admin` |
| Portal JWT (compatibility) | `Authorization: Bearer <portal-token>` | Existing API clients may continue sending a portal token as a bearer credential |
| LiteLLM key | `Authorization: Bearer <litellm-key>` | Identify and inspect that exact key; no bulk editing |
| Management key | `X-API-Key: <management-key>` | Administrator access for trusted automation |

Enable agent access with a long random secret:

```yaml
management_api_key: "replace-with-a-long-random-secret"
```

Automation should not use a shared local username and password. The management
key is currently one installation-wide administrator credential rather than
separate scoped agent identities. Protect it as a password, keep it out of logs
and source control, and rotate it if exposure is suspected.

Bulk key editing remains administrator-only. A user portal JWT and a LiteLLM
virtual key cannot authorize `PATCH /api/v1/keys/bulk`.

## Security behavior

- Signed OIDC state values expire after ten minutes and are bound to the browser
  with an HttpOnly, SameSite cookie.
- OIDC ID tokens are verified for signing key, issuer, audience, expiration, and
  the per-login nonce. Discovery and signing keys are cached, with an automatic
  refresh when an identity provider rotates its signing key.
- Repeated failed password sign-ins from one client are temporarily throttled.
- New portal sessions stay in an HttpOnly, SameSite cookie. The JWT is not placed
  in a redirect URL or browser-readable storage; explicit sign-out clears it.
  Cookie-authenticated mutations also reject unapproved cross-site origins.
- Secret comparisons use constant-time comparison where applicable.
- Local authentication performs a dummy hash for unknown users.
- Local role and active state are checked on every authenticated request.
- Users cannot disable themselves or remove their own administrator role through
  the API.
- Key, local-account, team, and bulk-edit mutations share a limit of five
  operations per identity per minute. The portal disables mutation controls and
  shows the cooldown after that allowance is exhausted.
- Bulk updates use a five-request concurrency bound.
- Included Nginx configurations set CSP, anti-clickjacking, MIME-sniffing, and
  referrer headers.

For production, replace all examples, use HTTPS, restrict configuration access,
rotate secrets regularly, and back up the account database or persistent volume.
See the [deployment guide](../DEPLOYMENT.md) for production topology.
