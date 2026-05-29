"""Tests for Microsoft Teams feedback notifications."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from cortex.config import settings
from cortex.notify.teams import notify_new_feedback


@pytest.mark.asyncio
async def test_notify_skips_when_webhook_unset(monkeypatch):
    monkeypatch.setattr(settings, "teams_webhook_url", "")

    with patch("cortex.notify.teams.httpx.AsyncClient") as mock_client_cls:
        await notify_new_feedback(
            path="feedback/2026-05-29T12-00-00.md",
            title="Feedback test",
            content="Hello",
            tags=["t1"],
            related_paths=[],
        )
        mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_notify_posts_adaptive_card(monkeypatch):
    monkeypatch.setattr(settings, "teams_webhook_url", "https://example.webhook.office.com/test")
    monkeypatch.setattr(settings, "teams_app_base_url", "https://cortex.example.com")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("cortex.notify.teams.httpx.AsyncClient", return_value=mock_client):
        await notify_new_feedback(
            path="feedback/2026-05-29T12-00-00.md",
            title="Feedback 2026-05-29T12:00:00Z",
            content="Search missed a doc.",
            tags=["search"],
            related_paths=["wiki/target.md"],
            status="OPEN",
            authored_by="api",
            created_at="2026-05-29T12:00:00+00:00",
        )

    mock_client.post.assert_awaited_once()
    call = mock_client.post.await_args
    assert call.args[0] == "https://example.webhook.office.com/test"
    payload = call.kwargs["json"]
    assert payload["type"] == "message"
    card = payload["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    text_blocks = [b["text"] for b in card["body"] if b.get("type") == "TextBlock"]
    assert "Search missed a doc." in text_blocks
    actions = [
        b for b in card["body"]
        if b.get("type") == "ActionSet"
    ]
    assert actions[0]["actions"][0]["url"] == (
        "https://cortex.example.com/api/v1/feedbacks/2026-05-29T12-00-00.md"
    )


@pytest.mark.asyncio
async def test_notify_logs_http_error_without_raising(monkeypatch):
    monkeypatch.setattr(settings, "teams_webhook_url", "https://example.webhook.office.com/test")

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad payload"

    def _raise_http_error(*_args, **_kwargs):
        raise httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_response
        )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=_raise_http_error)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("cortex.notify.teams.httpx.AsyncClient", return_value=mock_client):
        await notify_new_feedback(
            path="feedback/x.md",
            title="T",
            content="C",
            tags=[],
            related_paths=[],
        )


