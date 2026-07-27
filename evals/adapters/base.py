"""Adapter protocol — one interface for Cortex, baselines, and ablations."""
from __future__ import annotations

from typing import Any, Protocol


class SystemAdapter(Protocol):
    """A system under evaluation: ingest content, retrieve for a question."""

    @property
    def name(self) -> str:
        """Identifier recorded in every trace (e.g. 'cortex-hybrid')."""
        raise NotImplementedError

    async def ingest(self, filename: str, content: str) -> dict[str, Any]:
        """Feed one document/session into the system."""
        raise NotImplementedError

    async def retrieve(self, question: str) -> list[dict[str, Any]]:
        """Return retrieved context items [{path, snippet}] for a question."""
        raise NotImplementedError
