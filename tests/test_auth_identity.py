"""Tests for author identity resolution from auth claims."""
from __future__ import annotations

from cortex.auth.identity import author_from_claims


def test_author_from_claims_prefers_name() -> None:
    assert author_from_claims({"name": "Jane Doe", "email": "j@x.com"}) == "Jane Doe"


def test_author_from_claims_falls_back_to_email() -> None:
    assert author_from_claims({"email": "j@x.com"}) == "j@x.com"


def test_author_from_claims_api_key_only() -> None:
    assert author_from_claims({"auth_method": "api_key"}) is None
