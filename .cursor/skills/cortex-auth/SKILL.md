---
name: cortex-auth
description: >-
  Cortex authentication — AUTH_METHOD none/apikey/oidc, API_KEY, OIDC, middleware,
  MCP ApiKeyGuard. Use for login, x-api-key, or securing endpoints.
---

# Cortex auth

## Configuration (`cortex/config.py`)

| Env (also `CORTEX_*`) | Field | Purpose |
|------------------------|-------|---------|
| `AUTH_METHOD` | `auth_method` | `none`, `apikey`, `oidc` |
| `API_KEY` | `api_key` | Shared secret for REST + MCP |
| `OIDC_*` | `oidc_*` | Provider URLs, client id/secret, redirect |

Loaded via Pydantic Settings with `CORTEX_` prefix and unprefixed aliases in `.env`.

## REST middleware

`cortex/auth/middleware.py` — `AuthMiddleware` on FastAPI app.

**Public paths (no auth):**

- `/api/v1/health`, `/api/v1/login`, `/api/v1/auth/callback`
- `/mcp`, `/.well-known/`, `/docs`, `/redoc`, `/openapi.json`

**Protected:** all other `/api/v1/*`

| Mode | Client sends |
|------|----------------|
| `apikey` | Header `x-api-key: <API_KEY>` |
| `oidc` | `Authorization: Bearer <token>`; API key accepted as fallback if set |
| `none` | No credentials |

## MCP auth

`cortex/mcp/http_server.py` — `ApiKeyGuardMiddleware` when `auth_method == apikey`.

Clients (Cursor, curl) must send `x-api-key` on `POST /mcp/` and subsequent MCP requests.

## OIDC flow

1. `GET /api/v1/login` → redirect to IdP
2. `GET /api/v1/auth/callback` → exchange code, issue session/token
3. Use bearer token on API calls

FastMCP may use `OIDCProxy` for browser-based MCP login in oidc mode.

## Local development

```bash
AUTH_METHOD=none   # simplest
# or
AUTH_METHOD=apikey
API_KEY=dev-secret
```

`scripts/env_check.sh` prompts for auth-related vars when applying defaults.

## Related skills

- MCP HTTP: `cortex-mcp`
- Deploy secrets: `cortex-deploy`
