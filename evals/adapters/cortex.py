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
        context_chars: int = 0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.search_mode = search_mode
        self.top_k = top_k
        # When > 0, replace each hit's snippet with the full note content
        # (capped per note) — matching how agents consume Cortex: search,
        # then read the note.
        self.context_chars = context_chars
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

        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        for r in results:
            path = r.get("path", "")
            if path in seen:
                continue
            seen.add(path)
            hits.append(
                {"path": path, "snippet": r.get("snippet") or r.get("text") or ""}
            )

        if self.context_chars > 0:
            for hit in hits:
                content = await self._read_note(hit["path"])
                if content:
                    hit["snippet"] = content[: self.context_chars]
        return hits

    async def _read_note(self, path: str) -> str:
        """Fetch full note content; empty string when unavailable."""
        response = await self._client.get(f"/api/v1/notes/{path}")
        if response.status_code != 200:
            return ""
        return response.json().get("content", "")

    async def aclose(self) -> None:
        await self._client.aclose()
