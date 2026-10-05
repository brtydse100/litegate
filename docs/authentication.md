# Authentication and security

LiteGate supports browser sessions through OpenID Connect, generic OAuth SSO, or local accounts, and
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

LiteGate uses the issuer's discovery document by default. For providers that
require manual configuration, set all three endpoints together:

```yaml
oidc_authorization_endpoint: "https://login.example.com/oauth2/authorize"
oidc_token_endpoint: "https://login.example.com/oauth2/token"
oidc_jwks_uri: "https://login.example.com/oauth2/keys"
```

The issuer is still required for ID-token issuer validation. Manual mode keeps
the same authorization-code flow, signed state, nonce, and token verification;
it only replaces discovery of the provider endpoints.

## Generic OAuth SSO

Use this alternative when the provider exposes authorization, token, and
UserInfo endpoints, as in LiteLLM's generic OAuth setup. LiteGate exchanges the
authorization code, then calls UserInfo with the returned bearer access token.
Opaque access tokens are supported. This mode does not require an issuer,
ID token, discovery document, or JWKS endpoint.

In Docker Compose's `config.yaml`, leave the OIDC issuer/manual endpoints blank
and configure:

```yaml
root_url: "https://litegate.example.com"
generic_client_id: "litegate"
generic_client_secret: "replace-me"
generic_authorization_endpoint: "https://login.example.com/authorize"
generic_token_endpoint: "https://login.example.com/token"
generic_userinfo_endpoint: "https://login.example.com/userinfo"
generic_scope: "openid profile email"
generic_user_id_attribute: "sub"
generic_user_email_attribute: "email"
generic_client_use_pkce: true
```

The uppercase equivalents (`GENERIC_CLIENT_ID`, `GENERIC_USERINFO_ENDPOINT`,
`GENERIC_USER_ID_ATTRIBUTE`, etc.) override YAML. Register
`https://litegate.example.com/api/auth/callback` with the provider. The callback
defaults to `root_url` plus `/api/auth/callback`; use `generic_redirect_uri`
(`GENERIC_REDIRECT_URI`) when the backend has a different public origin or when
developing with separate frontend/backend ports.

Select the user ID/email fields returned by your provider. Dotted paths such as
`identity.employee_id` are supported. Use a unique, stable ID rather than an
editable email address. The default ID is `sub`; set it explicitly to the same
field used by your existing LiteLLM deployment when sharing users and keys.
LiteLLM's default generic ID field can differ. Changing the identity field or
OAuth client can change user IDs and produce separate LiteLLM user records.

The ID must be a nonempty string. Email may be absent, in which case email-based
administrator matching does not apply. A provided email must be a nonempty
string; an explicitly false `email_verified` value rejects login by default.
Set `generic_require_verified_email: false` (`GENERIC_REQUIRE_VERIFIED_EMAIL=false`,
Helm `config.genericRequireVerifiedEmail: false`) to allow it. A missing
`email_verified` claim remains accepted. This option applies only to generic
OAuth; OIDC email handling is unchanged. Allowing unverified email also permits
email-based administrator matching against that email, so use a provider that
controls the email attribute or assign administrators through trusted groups.
HTTP errors,
malformed provider responses, and missing IDs fail login without exposing
provider responses or credentials to the browser. HTTPS is required except on
localhost. Endpoint redirects are not followed.

Enable `generic_client_use_pkce` for providers requiring PKCE (S256). The
verifier is derived from the signed state and its signing secret; it is never
included in the authorization URL and survives configured signing-key rotation.
By default the token request carries client credentials in its body. Set
`generic_include_client_id: false` for HTTP Basic client authentication.

Both modes retain browser-bound signed state, HttpOnly sessions, existing
administrator rules, default teams, and group mappings. In generic mode,
`oidc_groups_claim` reads groups from UserInfo. Provider-supplied role fields do
not grant LiteGate administrative access.

Google and Microsoft Entra ID can use this flow with their UserInfo endpoints
and `openid profile email` scopes. Microsoft UserInfo may omit email and does
not return groups/custom claims. Use LiteGate's OIDC mode for groups included in
the ID token; resolving Microsoft group-overage claims through Graph is not
supported. See [Google UserInfo](https://developers.google.com/identity/openid-connect/reference)
and [Microsoft UserInfo](https://learn.microsoft.com/en-us/entra/identity-platform/userinfo).

This implements the core [LiteLLM generic OAuth flow](https://docs.litellm.ai/docs/proxy/admin_ui_sso)
and the configuration options listed above. LiteLLM custom Python SSO handlers,
custom request headers, static state values, token-claim merging, and its role
mapping options are not interpreted. OIDC mode continues to verify ID-token
signatures and claims; generic mode authenticates identity through UserInfo.

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

For OIDC, the provider must put the desired value directly in the ID token;
for generic OAuth, it must be present in UserInfo. Configure IDs
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

Set `sso_default_team_id` to add every SSO user to one existing LiteLLM team.
This membership is added alongside all group-mapped teams. The first mapped
team is primary for generated keys; when no group matches, the default team is
primary. The default team does not satisfy `oidc_require_team_mapping: true`,
which deliberately continues to require an explicit group mapping.

To reuse LiteLLM's platform-owner assignment, set `inherit_litellm_admin: true`.
LiteGate then grants its admin role only when the matching LiteLLM user has the
full `proxy_admin` role. It does not promote `proxy_admin_viewer`, organization
admins, or team admins because LiteGate admin operations are installation-wide
and can modify data.

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
- Session signing keys support zero-downtime rotation: `jwt_secret` signs new
  sessions and `jwt_previous_secrets` temporarily verifies sessions created
  before the rotation.
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
rotate secrets regularly, and use the verified database backup procedure rather
than copying an active SQLite file.
See the [deployment guide](../DEPLOYMENT.md) for production topology.
