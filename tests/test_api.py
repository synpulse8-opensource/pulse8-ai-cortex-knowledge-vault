from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_vault: Path):
    """Create a test client with a temporary vault."""
    import asyncio
    from cortex.graph.builder import build_graph
    from cortex.graph.engine import GraphEngine
    from cortex.search.qmd import QMDSearch
    from cortex.vault.reader import scan_vault

    from fastapi import FastAPI
    from cortex.api.routes import router

    test_app = FastAPI(title="Cortex Test")
    test_app.include_router(router, prefix="/api/v1")

    test_app.state.vault_path = tmp_vault

    graph = GraphEngine(tmp_vault / ".cortex" / "graph.json")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(graph.load())
    notes = scan_vault(tmp_vault)
    test_app.state.graph = loop.run_until_complete(
        build_graph(notes, tmp_vault / ".cortex" / "graph.json", tmp_vault)
    )
    test_app.state.qmd = QMDSearch(tmp_vault, "qmd")
    loop.close()

    client = TestClient(test_app)
    return client


class TestHealthEndpoint:
    def test_health(self, app_client):
        response = app_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestNotesEndpoints:
    def test_read_note(self, app_client):
        response = app_client.get("/api/v1/notes/wiki/transformers.md")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Transformer Architecture"

    def test_read_nonexistent_note(self, app_client):
        response = app_client.get("/api/v1/notes/wiki/nonexistent.md")
        assert response.status_code == 404

    def test_write_note(self, app_client):
        response = app_client.put(
            "/api/v1/notes/wiki/api-test.md",
            json={
                "content": "# API Test\n\nCreated via API.",
                "frontmatter": {"tags": ["api", "test"]},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "wiki/api-test.md"


class TestSearchEndpoint:
    def test_search(self, app_client):
        with patch("cortex.api.routes.get_qmd") as mock_qmd_getter:
            mock_qmd = AsyncMock()
            mock_qmd.search = AsyncMock(return_value=[
                {"path": "wiki/transformers.md", "score": 0.9, "snippet": "test"},
            ])
            mock_qmd_getter.return_value = mock_qmd

            response = app_client.get("/api/v1/search?q=transformer")
            assert response.status_code == 200


class TestLinksEndpoints:
    def test_create_link(self, app_client):
        response = app_client.post(
            "/api/v1/links",
            json={
                "source": "wiki/transformers.md",
                "target": "wiki/attention-mechanisms.md",
                "edge_type": "contradicts",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "created"

    def test_query_links(self, app_client):
        response = app_client.get("/api/v1/links?source=wiki/transformers.md")
        assert response.status_code == 200
        assert "edges" in response.json()


class TestGraphStatsEndpoint:
    def test_graph_stats(self, app_client):
        response = app_client.get("/api/v1/graph/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_nodes" in data
        assert "total_edges" in data


class TestIngestEndpoint:
    def test_ingest(self, app_client):
        response = app_client.post(
            "/api/v1/ingest",
            json={
                "content": "Raw content for ingestion.",
                "filename": "api-ingest.txt",
                "source_type": "text",
                "auto_compile": False,
            },
        )
        assert response.status_code == 200
        assert response.json()["path"] == "raw/api-ingest.txt"
