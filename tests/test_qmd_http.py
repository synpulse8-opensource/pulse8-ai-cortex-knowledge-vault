"""Tests for QMD HTTP search client."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestQMDHttpSearch:
    @pytest.mark.asyncio
    async def test_search_hybrid_via_http(self):
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer model"},
        ]

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            results = await qmd.search("transformers", mode="hybrid")
            assert len(results) == 1
            assert results[0]["score"] == 0.9
            mock_client.post.assert_called_once()
            call_json = mock_client.post.call_args[1]["json"]
            assert call_json["query"] == "transformers"
            assert call_json["mode"] == "hybrid"

    @pytest.mark.asyncio
    async def test_search_keyword_via_http(self):
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            await qmd.search("test", mode="keyword")
            call_json = mock_client.post.call_args[1]["json"]
            assert call_json["mode"] == "keyword"

    @pytest.mark.asyncio
    async def test_search_with_collection(self):
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            await qmd.search("test", collection="wiki")
            call_json = mock_client.post.call_args[1]["json"]
            assert call_json["collection"] == "wiki"

    @pytest.mark.asyncio
    async def test_search_handles_server_error(self):
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            results = await qmd.search("test")
            assert results == []

    @pytest.mark.asyncio
    async def test_search_handles_connection_error(self):
        import httpx
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            results = await qmd.search("test")
            assert results == []

    @pytest.mark.asyncio
    async def test_initialize_calls_setup(self):
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            await qmd.initialize()
            assert qmd._initialized is True
            mock_client.post.assert_called_once()
            assert "/setup" in mock_client.post.call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_calls_reindex(self):
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            await qmd.update()
            mock_client.post.assert_called_once()
            assert "/update" in mock_client.post.call_args[0][0]

    @pytest.mark.asyncio
    async def test_initialize_uses_extended_timeout(self):
        """initialize() must use a timeout of at least 300s for /setup."""
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            await qmd.initialize()
            call_kwargs = mock_client.post.call_args[1]
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] >= 300

    @pytest.mark.asyncio
    async def test_initialize_tolerates_timeout_error(self):
        """initialize() should degrade gracefully on timeout."""
        import httpx
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.ReadTimeout("Setup timed out"))
            await qmd.initialize()
            assert qmd._initialized is False

    @pytest.mark.asyncio
    async def test_update_uses_extended_timeout(self):
        """update() must use a timeout >= 120s to survive long embed runs."""
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            await qmd.update()
            call_kwargs = mock_client.post.call_args[1]
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] >= 120

    @pytest.mark.asyncio
    async def test_search_uses_configurable_timeout(self, monkeypatch):
        """search() must use settings.qmd_search_timeout_seconds, not the 30s client default.

        Hybrid mode on CPU-only hosts routinely exceeds 30s; the timeout
        made Cortex silently return [] while QMD was still working.
        """
        from cortex.config import settings as app_settings
        from cortex.search.qmd_http import QMDHttpSearch

        monkeypatch.setattr(app_settings, "qmd_search_timeout_seconds", 240.0)

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            await qmd.search("query", mode="hybrid")
            call_kwargs = mock_client.post.call_args[1]
            assert call_kwargs.get("timeout") == 240.0

    @pytest.mark.asyncio
    async def test_initialize_polls_health_before_calling_setup(self):
        """If /health shows setup_ready=true, skip /setup entirely."""
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "ok", "setup_ready": True}

        with patch.object(qmd, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=health_response)
            mock_client.post = AsyncMock()
            await qmd.initialize()
            assert qmd._initialized is True
            mock_client.get.assert_awaited()
            mock_client.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_initialize_calls_setup_when_not_ready(self):
        """If /health shows setup_ready=false, fall back to /setup."""
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "ok", "setup_ready": False}

        setup_response = MagicMock()
        setup_response.status_code = 200
        setup_response.raise_for_status = MagicMock()

        with patch.object(qmd, "_client") as mock_client:
            mock_client.get = AsyncMock(return_value=health_response)
            mock_client.post = AsyncMock(return_value=setup_response)
            await qmd.initialize()
            assert qmd._initialized is True
            mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_falls_back_on_health_failure(self):
        """If /health fails, fall back to calling /setup."""
        import httpx
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")

        setup_response = MagicMock()
        setup_response.status_code = 200
        setup_response.raise_for_status = MagicMock()

        with patch.object(qmd, "_client") as mock_client, \
             patch("cortex.search.qmd_http.asyncio.sleep", new_callable=AsyncMock):
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
            mock_client.post = AsyncMock(return_value=setup_response)
            await qmd.initialize()
            assert qmd._initialized is True
            mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_normalizes_qmd_file_field_to_path(self):
        """QMD returns 'file' with qmd:// prefix; search() must map it to 'path'."""
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "docid": "#abc123",
                "score": 0.9,
                "file": "qmd://wiki/transformer-architecture.md",
                "title": "Transformer Architecture",
                "snippet": "some snippet",
            },
            {
                "docid": "#def456",
                "score": 0.7,
                "file": "qmd://wiki/attention.md",
                "title": "Attention",
                "snippet": "attention snippet",
            },
        ]

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            results = await qmd.search("transformer", mode="keyword")

            assert len(results) == 2
            assert results[0]["path"] == "wiki/transformer-architecture.md"
            assert results[1]["path"] == "wiki/attention.md"
            assert "qmd://" not in results[0].get("path", "")

    @pytest.mark.asyncio
    async def test_search_normalizes_file_without_qmd_prefix(self):
        """If QMD returns a file without qmd:// prefix, still map to path."""
        from cortex.search.qmd_http import QMDHttpSearch

        qmd = QMDHttpSearch(base_url="http://qmd:3100")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"score": 0.8, "file": "wiki/test.md", "title": "Test"},
        ]

        with patch.object(qmd, "_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            results = await qmd.search("test")
            assert results[0]["path"] == "wiki/test.md"

    @pytest.mark.asyncio
    async def test_has_same_interface_as_qmd_search(self):
        """QMDHttpSearch must have the same public API as QMDSearch."""
        from cortex.search.qmd_http import QMDHttpSearch
        from cortex.search.qmd import QMDSearch

        http_methods = {m for m in dir(QMDHttpSearch) if not m.startswith("_")}
        cli_methods = {m for m in dir(QMDSearch) if not m.startswith("_")}
        required = {"search", "initialize", "update"}
        assert required.issubset(http_methods)
        assert required.issubset(cli_methods)
