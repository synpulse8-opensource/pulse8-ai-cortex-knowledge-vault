"""HTTP client for a remote QMD search container."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class QMDHttpSearch:
    """HTTP client for a QMD search service running in a separate container."""

    def __init__(self, base_url: str = "http://localhost:3100") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        self._initialized = False

    async def initialize(self) -> None:
        """Wait for the QMD server to be ready, falling back to ``/setup``.

        The QMD container auto-runs setup on start.  We first check
        ``/health`` and only call ``/setup`` if the container hasn't
        finished its own initialization.  This avoids running the
        expensive setup twice.
        """
        try:
            resp = await self._client.get("/health")
            if resp.status_code == 200 and resp.json().get("setup_ready"):
                self._initialized = True
                return
        except Exception:
            logger.debug("QMD /health check failed, falling back to /setup")

        try:
            resp = await self._client.post("/setup", timeout=300.0)
            resp.raise_for_status()
            self._initialized = True
        except Exception:
            logger.exception("QMD HTTP initialization failed")

    async def update(self) -> None:
        """Trigger re-index and re-embed on the QMD server.

        Uses a 10-minute timeout because the server-side embed step
        can take up to 600s on large vaults.
        """
        try:
            resp = await self._client.post("/update", timeout=600.0)
            resp.raise_for_status()
        except Exception:
            logger.exception("QMD HTTP update failed")

    @staticmethod
    def _normalize_results(raw: list[dict]) -> list[dict]:
        """Map QMD response fields to the schema Cortex expects.

        QMD returns ``file`` with a ``qmd://`` URI prefix; Cortex handlers
        look up results by ``path`` (vault-relative, no prefix).
        """
        normalized = []
        for r in raw:
            entry = dict(r)
            file_val = entry.pop("file", "")
            if file_val.startswith("qmd://"):
                file_val = file_val[len("qmd://"):]
            entry.setdefault("path", file_val)
            normalized.append(entry)
        return normalized

    async def search(
        self,
        query: str,
        mode: str = "hybrid",
        collection: str | None = None,
        top_k: int = 10,
    ) -> list[dict]:
        """Search via the QMD HTTP API."""
        payload: dict = {
            "query": query,
            "mode": mode,
            "top_k": top_k,
        }
        if collection:
            payload["collection"] = collection

        try:
            resp = await self._client.post("/search", json=payload)
            if resp.status_code != 200:
                logger.warning("QMD search returned %d", resp.status_code)
                return []
            return self._normalize_results(resp.json())
        except Exception:
            logger.warning("QMD search unavailable")
            return []

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
