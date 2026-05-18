"""Tests for REST API routes."""
from __future__ import annotations

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
    from cortex.search.qmd_debounce import DebouncedQMDUpdate
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
    test_app.state.qmd_debounce = DebouncedQMDUpdate(test_app.state.qmd)
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

    def test_write_note_schedules_debounced_qmd_update(self, app_client):
        with patch.object(app_client.app.state.qmd_debounce, "schedule") as mock_schedule:
            response = app_client.put(
                "/api/v1/notes/wiki/qmd-refresh-api.md",
                json={
                    "content": "# QMD Refresh\n\nShould trigger debounced update.",
                },
            )
            assert response.status_code == 200
            mock_schedule.assert_called_once()


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

    def test_ingest_schedules_debounced_qmd_update(self, app_client):
        with patch.object(app_client.app.state.qmd_debounce, "schedule") as mock_schedule:
            response = app_client.post(
                "/api/v1/ingest",
                json={
                    "content": "Raw content for QMD refresh test.",
                    "filename": "qmd-refresh-ingest.txt",
                    "source_type": "text",
                    "auto_compile": False,
                },
            )
            assert response.status_code == 200
            mock_schedule.assert_called_once()


class TestIngestUploadEndpoint:
    def test_upload_binary_file(self, app_client):
        """POST /ingest/upload should accept a multipart file upload."""
        content = b"<html><body><h1>Uploaded</h1></body></html>"
        response = app_client.post(
            "/api/v1/ingest/upload",
            files={"file": ("page.html", content, "text/html")},
            data={"auto_compile": "false"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "raw/page.html"
        assert data["status"] == "ingested"

    def test_upload_with_auto_compile(self, app_client):
        """Upload with auto_compile should convert the file to wiki markdown."""
        content = b"<html><body><h1>CompileMe</h1><p>Body text.</p></body></html>"
        response = app_client.post(
            "/api/v1/ingest/upload",
            files={"file": ("compile-me.html", content, "text/html")},
            data={"auto_compile": "true"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("compiled") is True
        assert len(data.get("wiki_articles", [])) >= 1

    def test_upload_preserves_original_bytes(self, app_client):
        """Uploaded binary content should be written exactly as received."""
        binary = b"\x89PNG\r\n\x1a\nfake-png-data"
        response = app_client.post(
            "/api/v1/ingest/upload",
            files={"file": ("image.png", binary, "image/png")},
            data={"auto_compile": "false"},
        )
        assert response.status_code == 200
        vault_path = app_client.app.state.vault_path
        assert (vault_path / "raw" / "image.png").read_bytes() == binary


class TestCompileEndpoint:
    def test_compile_schedules_debounced_qmd_update(self, app_client):
        vault_path = app_client.app.state.vault_path
        (vault_path / "raw" / "compile-api-test.txt").write_text("Compile me via API.")

        with patch.object(app_client.app.state.qmd_debounce, "schedule"):
            with patch("cortex.compiler.compiler.KnowledgeCompiler"):
                response = app_client.post("/api/v1/compile")
            assert response.status_code == 202
            assert response.json()["status"] == "accepted"


class TestBulkIngestEndpoint:
    def test_bulk_ingest_requires_source_dir(self, app_client):
        response = app_client.post(
            "/api/v1/bulk-ingest",
            json={"source_dir": "/nonexistent/path"},
        )
        assert response.status_code == 400

    def test_bulk_ingest_success(self, app_client):
        vault_path = app_client.app.state.vault_path
        inbox = vault_path.parent / "inbox"
        inbox.mkdir()
        (inbox / "test.txt").write_text("Bulk ingest test content")

        mock_result = {
            "copied": ["test.txt"],
            "skipped": [],
            "compiled": ["wiki/test.md"],
            "dry_run": False,
        }

        with patch("cortex.compiler.bulk.BulkIngestor") as mock_cls:
            instance = mock_cls.return_value
            instance.run = AsyncMock(return_value=mock_result)

            response = app_client.post(
                "/api/v1/bulk-ingest",
                json={"source_dir": str(inbox)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["copied"] == ["test.txt"]
        assert data["compiled"] == ["wiki/test.md"]

    def test_bulk_ingest_dry_run(self, app_client):
        vault_path = app_client.app.state.vault_path
        inbox = vault_path.parent / "inbox-dry"
        inbox.mkdir()
        (inbox / "test.txt").write_text("Dry run test")

        mock_result = {
            "copied": ["test.txt"],
            "skipped": [],
            "compiled": [],
            "dry_run": True,
        }

        with patch("cortex.compiler.bulk.BulkIngestor") as mock_cls:
            instance = mock_cls.return_value
            instance.run = AsyncMock(return_value=mock_result)

            response = app_client.post(
                "/api/v1/bulk-ingest",
                json={"source_dir": str(inbox), "dry_run": True},
            )

        assert response.status_code == 200
        assert response.json()["dry_run"] is True

    def test_bulk_ingest_passes_all_options(self, app_client):
        vault_path = app_client.app.state.vault_path
        inbox = vault_path.parent / "inbox-opts"
        inbox.mkdir()
        (inbox / "test.txt").write_text("Options test")

        with patch("cortex.compiler.bulk.BulkIngestor") as mock_cls:
            instance = mock_cls.return_value
            instance.run = AsyncMock(return_value={
                "copied": [], "skipped": [], "compiled": [], "dry_run": False,
            })

            response = app_client.post(
                "/api/v1/bulk-ingest",
                json={
                    "source_dir": str(inbox),
                    "concurrency": 8,
                    "force": True,
                    "dry_run": False,
                },
            )

        assert response.status_code == 200
        mock_cls.assert_called_once_with(
            vault_path=vault_path,
            source_dir=inbox,
            concurrency=8,
            force=True,
            dry_run=False,
        )
