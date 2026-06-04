"""Resolve a display name for the authenticated caller."""
from __future__ import annotations

from typing import Any


def author_from_claims(claims: dict[str, Any] | None) -> str | None:
    """Pick a human-readable author from OIDC/JWT claims, if present."""
    if not claims:
        return None
    for key in ("name", "preferred_username", "email", "upn"):
        value = claims.get(key)
        if value:
            return str(value)
    return None
