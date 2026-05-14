"""JWT token validation against Microsoft Entra ID (Azure AD) JWKS."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from cortex.config import settings

logger = logging.getLogger(__name__)

_JWKS_CLIENT: PyJWKClient | None = None
_JWKS_CLIENT_TS: float = 0.0
_JWKS_CACHE_TTL = 3600  # re-create client every hour to refresh keys


def _get_jwks_client() -> PyJWKClient:
    """Return a cached PyJWKClient, refreshing after TTL expires."""
    global _JWKS_CLIENT, _JWKS_CLIENT_TS  # pylint: disable=global-statement

    now = time.monotonic()
    if _JWKS_CLIENT is None or (now - _JWKS_CLIENT_TS) > _JWKS_CACHE_TTL:
        jwks_uri = _discover_jwks_uri()
        _JWKS_CLIENT = PyJWKClient(jwks_uri, cache_keys=True)
        _JWKS_CLIENT_TS = now
        logger.info("JWKS client initialised from %s", jwks_uri)

    return _JWKS_CLIENT


def _discover_jwks_uri() -> str:
    """Fetch the JWKS URI from the OIDC discovery document."""
    resp = httpx.get(settings.oidc_config_url, timeout=10)
    resp.raise_for_status()
    uri = resp.json()["jwks_uri"]
    return uri


def validate_token(token: str) -> dict[str, Any]:
    """Decode and validate a Bearer token.

    Returns the decoded claims dict on success.
    Raises ``jwt.InvalidTokenError`` (or subclass) on failure.
    """
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)

    decoded = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer,
        options={"require": ["exp", "iss", "aud"]},
    )
    return decoded
