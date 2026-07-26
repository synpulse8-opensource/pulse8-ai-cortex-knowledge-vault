"""Cortex adapter — evaluates the full ingest -> compile -> search pipeline
through the public REST API, exactly as a user deployment would run it."""
from __future__ import annotations

from typing import Any

import httpx


class CortexAdapter:
    """Talks to a running Cortex instance over REST."""

    def __init__(
        self,
        base_url: str,
        search_mode: str = "hybrid",
        top_k: int = 8,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.search_mode = search_mode
        self.top_k = top_k
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url, timeout=300.0
        )

    @property
    def name(self) -> str:
        return f"cortex-{self.search_mode}"

    async def ingest(self, filename: str, content: str) -> dict[str, Any]:
        """Ingest one document/session as a raw source (auto-compiled)."""
        response = await self._client.post(
            "/api/v1/ingest",
            json={"content": content, "filename": filename, "auto_compile": True},
        )
        response.raise_for_status()
        return response.json()

    async def retrieve(self, question: str) -> list[dict[str, Any]]:
        """Search the vault and normalize results to [{path, snippet}]."""
        response = await self._client.get(
            "/api/v1/search",
            params={"q": question, "mode": self.search_mode, "top_k": self.top_k},
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [
            {
                "path": r.get("path", ""),
                "snippet": r.get("snippet") or r.get("text") or "",
            }
            for r in results
        ]

    async def aclose(self) -> None:
        await self._client.aclose()
