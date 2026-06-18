"""Server-side MCP resource store.

Implements the "resources as tool inputs" pattern recommended by the
Microsoft Copilot Studio CAT team: token-heavy tool outputs are kept
server-side and addressed by short resource IDs, so the LLM context
window stays small while the data remains available for downstream
tools and resource reads.

The store is intentionally in-memory and asyncio-safe; persistence is
not a goal — these are ephemeral handles, not vault content.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

_DEFAULT_TTL = timedelta(hours=1)
_DEFAULT_MAX_ITEMS = 1000


@dataclass
class StoredResource:
    """A single entry held by :class:`ResourceStore`."""

    content: str
    mime_type: str = "text/plain"
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: datetime | None = None


class ResourceStore:
    """Asyncio-safe, in-memory key/value store for MCP resources.

    Entries are evicted lazily on :py:meth:`get` once their TTL elapses,
    so the store never spins a background task. A bounded LRU cap
    (``max_items``) prevents unbounded memory growth.
    """

    def __init__(
        self,
        default_ttl: timedelta = _DEFAULT_TTL,
        max_items: int = _DEFAULT_MAX_ITEMS,
    ) -> None:
        if max_items < 1:
            raise ValueError("max_items must be >= 1")
        self._lock = asyncio.Lock()
        self._items: OrderedDict[str, StoredResource] = OrderedDict()
        self._default_ttl = default_ttl
        self._max_items = max_items

    @classmethod
    def from_settings(cls, settings: Any) -> "ResourceStore":
        """Build a store using ``CortexSettings.resource_*`` values."""
        return cls(
            default_ttl=timedelta(seconds=settings.resource_ttl_seconds),
            max_items=settings.resource_max_items,
        )

    async def put(
        self,
        content: str,
        *,
        mime_type: str = "text/plain",
        ttl: timedelta | None = None,
    ) -> str:
        """Store *content* and return its resource ID."""
        resource_id = uuid.uuid4().hex
        effective_ttl = ttl if ttl is not None else self._default_ttl
        now = datetime.now(timezone.utc)
        resource = StoredResource(
            content=content,
            mime_type=mime_type,
            created_at=now,
            expires_at=now + effective_ttl,
        )
        async with self._lock:
            self._items[resource_id] = resource
            self._items.move_to_end(resource_id)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)
        return resource_id

    async def get(self, resource_id: str) -> StoredResource | None:
        """Fetch a stored resource by ID, or ``None`` if absent or expired."""
        async with self._lock:
            entry = self._items.get(resource_id)
            if entry is None:
                return None
            if entry.expires_at is not None and entry.expires_at <= datetime.now(
                timezone.utc
            ):
                self._items.pop(resource_id, None)
                return None
            self._items.move_to_end(resource_id)
            return entry
