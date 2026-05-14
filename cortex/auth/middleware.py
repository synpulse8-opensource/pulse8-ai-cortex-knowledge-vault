"""FastAPI middleware that enforces Bearer-token authentication on REST API routes."""
from __future__ import annotations

import logging

import jwt as pyjwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from cortex.auth.jwt import validate_token

logger = logging.getLogger(__name__)

UNPROTECTED_PREFIXES = (
    "/api/v1/health",
    "/api/v1/login",
    "/.well-known/",
    "/mcp",
)


class OIDCAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests to ``/api/*`` that lack a valid Bearer token.

    Paths in ``UNPROTECTED_PREFIXES`` are always allowed through.
    Non-API paths (e.g. ``/mcp``, ``/.well-known``) are also skipped
    because MCP has its own OIDCProxy auth layer.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if any(path.startswith(p) for p in UNPROTECTED_PREFIXES):
            return await call_next(request)

        if not path.startswith("/api/"):
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
