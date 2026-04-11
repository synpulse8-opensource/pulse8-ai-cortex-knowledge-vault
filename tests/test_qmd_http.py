from __future__ import annotations

import json
from pathlib import Path
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
    async def test_has_same_interface_as_qmd_search(self):
        """QMDHttpSearch must have the same public API as QMDSearch."""
        from cortex.search.qmd_http import QMDHttpSearch
        from cortex.search.qmd import QMDSearch

        http_methods = {m for m in dir(QMDHttpSearch) if not m.startswith("_")}
        cli_methods = {m for m in dir(QMDSearch) if not m.startswith("_")}
        required = {"search", "initialize", "update"}
        assert required.issubset(http_methods)
        assert required.issubset(cli_methods)
