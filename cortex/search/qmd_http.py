"""HTTP client for a remote QMD search container."""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class QMDHttpSearch:
    """HTTP client for a QMD search service running in a separate container."""

    def __init__(self, base_url: str = "http://localhost:3100") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)
        self._initialized = False

    async def initialize(self, retries: int = 10, delay: float = 3.0) -> None:
        """Wait for QMD to become reachable, then confirm it's ready.

        Retries with exponential backoff to handle the case where QMD
        starts after Cortex (common in Kubernetes without init containers).
        """
        for attempt in range(1, retries + 1):
            try:
                resp = await self._client.get("/health")
                if resp.status_code == 200 and resp.json().get("setup_ready"):
                    self._initialized = True
                    logger.info("QMD ready (attempt %d)", attempt)
                    return
            except (httpx.ConnectError, httpx.ConnectTimeout):
                wait = min(delay * attempt, 30.0)
                logger.info(
                    "QMD not reachable (attempt %d/%d), retrying in %.0fs",
                    attempt, retries, wait,
                )
                await asyncio.sleep(wait)
                continue
            except Exception:
                break

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

        from cortex.config import settings

        try:
            resp = await self._client.post(
                "/search", json=payload, timeout=settings.qmd_search_timeout_seconds
            )
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
