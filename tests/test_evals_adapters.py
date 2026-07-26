"""Tests for eval system adapters (offline via httpx.MockTransport)."""
from __future__ import annotations

import json

import httpx
import pytest


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://cortex.test"
    )


class TestCortexAdapter:
    def test_name_encodes_search_mode(self):
        from evals.adapters.cortex import CortexAdapter

        adapter = CortexAdapter(base_url="http://cortex.test", search_mode="hybrid")
        assert adapter.name == "cortex-hybrid"

    @pytest.mark.asyncio
    async def test_ingest_posts_to_rest_api(self):
        from evals.adapters.cortex import CortexAdapter

        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"status": "created"})

        adapter = CortexAdapter(
            base_url="http://cortex.test", client=_mock_client(handler)
        )
        result = await adapter.ingest("session-01.md", "# Session 1\n\nContent.")

        assert result["status"] == "created"
        assert captured["url"].endswith("/api/v1/ingest")
        assert captured["body"]["filename"] == "session-01.md"
        assert captured["body"]["content"].startswith("# Session 1")

    @pytest.mark.asyncio
    async def test_retrieve_maps_search_results(self):
        from evals.adapters.cortex import CortexAdapter

        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["params"] = dict(request.url.params)
            return httpx.Response(
                200,
                json={
                    "query": "zurich",
                    "results": [
                        {"path": "wiki/session-12.md", "snippet": "moved to Zurich"},
                        {"path": "wiki/session-03.md", "text": "fallback text"},
                    ],
                },
            )

        adapter = CortexAdapter(
            base_url="http://cortex.test",
            search_mode="keyword",
            top_k=5,
            client=_mock_client(handler),
        )
        results = await adapter.retrieve("zurich")

        assert captured["params"]["q"] == "zurich"
        assert captured["params"]["mode"] == "keyword"
        assert captured["params"]["top_k"] == "5"
        assert results[0] == {"path": "wiki/session-12.md", "snippet": "moved to Zurich"}
        # Falls back to `text` when no snippet field is present.
        assert results[1] == {"path": "wiki/session-03.md", "snippet": "fallback text"}
