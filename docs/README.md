# LiteGate documentation

Use this page as the entry point for detailed LiteGate documentation.

## Guides

| Guide | Use it when you want to... |
| --- | --- |
| [Features and access model](features.md) | Understand what users, administrators, and agents can do |
| [Authentication and security](authentication.md) | Configure OIDC, local users, roles, or API credentials |
| [Configuration reference](configuration.md) | Set portal behavior, key defaults, and integrations |
| [Deployment guide](../DEPLOYMENT.md) | Run LiteGate with Docker Compose or Kubernetes/Helm |
| [API v1 guide](../API.md) | Integrate an automation agent or call an endpoint |
| [Development guide](development.md) | Run, test, or understand the source tree |

## Important authorization boundary

Bulk key editing is an administrator-only operation in both the web portal and
the API. A normal user can create, inspect, and regenerate their personal key,
but cannot open the bulk editor or call `PATCH /api/v1/keys/bulk` successfully.

Trusted automation agents use the optional installation-wide
`management_api_key` and send it in the `X-API-Key` header. This credential has
administrator access and must be protected and rotated like any other privileged
secret.

## Other resources

- The Docker Compose example is in [`deploy/docker-compose`](../deploy/docker-compose/).
- The Helm chart is in [`deploy/helm/litegate`](../deploy/helm/litegate/).
- A ready-to-copy environment template is in [`.env.example`](../.env.example).
- A deployed instance serves Swagger UI at `/api/docs`, ReDoc at `/api/redoc`,
  and OpenAPI JSON at `/api/openapi.json`.
