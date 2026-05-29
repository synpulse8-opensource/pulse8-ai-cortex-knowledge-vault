"""Microsoft Teams notifications via Incoming Webhook / Workflow URL."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from cortex.config import settings

logger = logging.getLogger(__name__)

_CONTENT_MAX = 500


def _truncate(text: str, limit: int = _CONTENT_MAX) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _feedback_card_payload(
    *,
    path: str,
    title: str,
    content: str,
    tags: list[str],
    related_paths: list[str],
    status: str,
    authored_by: str,
    created_at: str | None,
    detail_url: str | None,
) -> dict[str, Any]:
    facts: list[dict[str, str]] = [
        {"title": "Status", "value": status},
        {"title": "Path", "value": path},
        {"title": "Author", "value": authored_by},
    ]
    if created_at:
        facts.append({"title": "Created", "value": created_at})
    if tags:
        facts.append({"title": "Tags", "value": ", ".join(tags)})
    if related_paths:
        facts.append({"title": "Related", "value": ", ".join(related_paths)})

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "size": "Medium",
            "weight": "Bolder",
            "text": title,
        },
        {
            "type": "TextBlock",
            "text": _truncate(content),
            "wrap": True,
        },
        {"type": "FactSet", "facts": facts},
    ]

    if detail_url:
        body.append({
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "View in Cortex",
                    "url": detail_url,
                }
            ],
        })

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                },
            }
        ],
    }


def _feedback_detail_url(path: str) -> str | None:
    base = (settings.teams_app_base_url or settings.oidc_base_url or "").strip().rstrip("/")
    if not base:
        return None
    filename = path.split("/")[-1]
    return f"{base}/api/v1/feedbacks/{filename}"


async def notify_new_feedback(
    *,
    path: str,
    title: str,
    content: str,
    tags: list[str],
    related_paths: list[str],
    status: str = "OPEN",
    authored_by: str = "human",
    created_at: str | None = None,
) -> None:
    """Post a Teams message when feedback is created. No-op if webhook URL is unset."""
    webhook_url = settings.teams_webhook_url.strip()
    if not webhook_url:
        return

    payload = _feedback_card_payload(
        path=path,
        title=title,
        content=content,
        tags=tags,
        related_paths=related_paths,
        status=status,
        authored_by=authored_by,
        created_at=created_at,
        detail_url=_feedback_detail_url(path),
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
        logger.info("Teams notification sent for feedback %s", path)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Teams webhook returned %s for feedback %s: %s",
            exc.response.status_code,
            path,
            exc.response.text[:200],
        )
    except Exception as exc:
        logger.warning("Failed to send Teams notification for %s: %s", path, exc)
