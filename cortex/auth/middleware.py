"""FastAPI middleware that enforces authentication on REST API routes.

Supports two authentication methods:
- ``x-api-key`` header: static API key (checked against ``settings.api_key``)
- ``Authorization: Bearer <token>``: JWT validated against Microsoft Entra ID JWKS
"""
from __future__ import annotations

import logging

import jwt as pyjwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from cortex.auth.jwt import validate_token
from cortex.config import settings

logger = logging.getLogger(__name__)

UNPROTECTED_PREFIXES = (
    "/api/v1/health",
    "/api/v1/login",
    "/api/v1/auth/callback",
    "/.well-known/",
    "/mcp",
)


class OIDCAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests to ``/api/*`` that lack valid credentials.

    Accepts either an ``x-api-key`` header matching the configured API key,
    or a ``Authorization: Bearer <JWT>`` validated against Microsoft JWKS.

    Paths in ``UNPROTECTED_PREFIXES`` are always allowed through.
    Non-API paths (e.g. ``/mcp``, ``/.well-known``) are also skipped
    because MCP has its own auth layer.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if any(path.startswith(p) for p in UNPROTECTED_PREFIXES):
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)

        api_key = request.headers.get("x-api-key", "")
        if api_key and settings.api_key and api_key == settings.api_key:
            request.state.user_claims = {"auth_method": "api_key"}
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse(
                {"detail": "Missing or invalid Authorization header"},
                status_code=401,
            )

        token = auth_header[7:]
        try:
            claims = validate_token(token)
            request.state.user_claims = claims
        except pyjwt.ExpiredSignatureError:
            logger.info("Rejected expired token for %s", path)
            return JSONResponse({"detail": "Token expired"}, status_code=401)
        except pyjwt.InvalidTokenError as exc:
            logger.info("Rejected invalid token for %s: %s", path, exc)
            return JSONResponse({"detail": "Invalid token"}, status_code=401)

        return await call_next(request)
