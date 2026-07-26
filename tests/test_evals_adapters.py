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

    @pytest.mark.asyncio
    async def test_retrieve_dedupes_and_fetches_full_notes(self):
        """With context_chars set, each unique hit carries full note content
        (capped), not just the search snippet — matching how agents actually
        consume Cortex (search, then read)."""
        from evals.adapters.cortex import CortexAdapter

        note_bodies = {
            "wiki/session-12.md": "# Session 12\n\n" + "moved to Zurich in March. " * 40,
            "wiki/session-03.md": "# Session 3\n\nshort note",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/search":
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {"path": "wiki/session-12.md", "snippet": "s1"},
                            {"path": "wiki/session-12.md", "snippet": "s1-dup"},
                            {"path": "wiki/session-03.md", "snippet": "s3"},
                        ]
                    },
                )
            if request.url.path.startswith("/api/v1/notes/"):
                path = request.url.path.removeprefix("/api/v1/notes/")
                return httpx.Response(
                    200, json={"path": path, "content": note_bodies[path]}
                )
            return httpx.Response(404)

        adapter = CortexAdapter(
            base_url="http://cortex.test",
            context_chars=200,
            client=_mock_client(handler),
        )
        results = await adapter.retrieve("zurich")

        # Duplicate paths collapse to one entry, order preserved.
        assert [r["path"] for r in results] == [
            "wiki/session-12.md",
            "wiki/session-03.md",
        ]
        # Full note content, capped at context_chars.
        assert results[0]["snippet"].startswith("# Session 12")
        assert len(results[0]["snippet"]) == 200
        assert results[1]["snippet"] == "# Session 3\n\nshort note"

    @pytest.mark.asyncio
    async def test_retrieve_falls_back_to_snippet_when_note_fetch_fails(self):
        from evals.adapters.cortex import CortexAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/search":
                return httpx.Response(
                    200,
                    json={"results": [{"path": "wiki/gone.md", "snippet": "snip"}]},
                )
            return httpx.Response(404, json={"detail": "not found"})

        adapter = CortexAdapter(
            base_url="http://cortex.test",
            context_chars=500,
            client=_mock_client(handler),
        )
        results = await adapter.retrieve("q")
        assert results == [{"path": "wiki/gone.md", "snippet": "snip"}]
