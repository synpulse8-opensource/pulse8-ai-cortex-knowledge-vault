from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestQMDSearch:
    @pytest.mark.asyncio
    async def test_search_hybrid(self):
        from cortex.search.qmd import QMDSearch

        qmd = QMDSearch(Path("/tmp/vault"), "qmd")
        mock_result = json.dumps([
            {"path": "wiki/transformers.md", "score": 0.9, "snippet": "transformer model"},
        ])

        with patch.object(qmd, "_run", new_callable=AsyncMock, return_value=mock_result):
            results = await qmd.search("transformers", mode="hybrid")
            assert len(results) == 1
            assert results[0]["score"] == 0.9

    @pytest.mark.asyncio
    async def test_search_keyword(self):
        from cortex.search.qmd import QMDSearch

        qmd = QMDSearch(Path("/tmp/vault"), "qmd")
        mock_result = json.dumps([])

        with patch.object(qmd, "_run", new_callable=AsyncMock, return_value=mock_result) as mock_run:
            await qmd.search("test", mode="keyword")
            args = mock_run.call_args[0][0]
            assert args[0] == "search"

    @pytest.mark.asyncio
    async def test_search_semantic(self):
        from cortex.search.qmd import QMDSearch

        qmd = QMDSearch(Path("/tmp/vault"), "qmd")
        mock_result = json.dumps([])

        with patch.object(qmd, "_run", new_callable=AsyncMock, return_value=mock_result) as mock_run:
            await qmd.search("test", mode="semantic")
            args = mock_run.call_args[0][0]
            assert args[0] == "vsearch"

    @pytest.mark.asyncio
    async def test_search_with_collection(self):
        from cortex.search.qmd import QMDSearch

        qmd = QMDSearch(Path("/tmp/vault"), "qmd")
        mock_result = json.dumps([])

        with patch.object(qmd, "_run", new_callable=AsyncMock, return_value=mock_result) as mock_run:
            await qmd.search("test", collection="wiki")
            args = mock_run.call_args[0][0]
            assert "-c" in args
            assert "wiki" in args

    @pytest.mark.asyncio
    async def test_search_handles_invalid_json(self):
        from cortex.search.qmd import QMDSearch

        qmd = QMDSearch(Path("/tmp/vault"), "qmd")

        with patch.object(qmd, "_run", new_callable=AsyncMock, return_value="not json"):
            results = await qmd.search("test")
            assert results == []

    @pytest.mark.asyncio
    async def test_initialize_adds_collections(self):
        from cortex.search.qmd import QMDSearch

        qmd = QMDSearch(Path("/tmp/vault"), "qmd")

        with patch.object(qmd, "_run", new_callable=AsyncMock, return_value="") as mock_run:
            await qmd.initialize()
            assert mock_run.call_count >= 6
            assert qmd._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_tolerates_existing_collections(self):
        """initialize() should not fail when collections already exist."""
        from cortex.search.qmd import QMDSearch

        qmd = QMDSearch(Path("/tmp/vault"), "qmd")

        call_count = 0

        async def _mock_run(args: list[str]) -> str:
            nonlocal call_count
            call_count += 1
            if args[0] == "collection" and args[1] == "add":
                raise RuntimeError("QMD error: Collection 'wiki' already exists.")
            return ""

        with patch.object(qmd, "_run", side_effect=_mock_run):
            await qmd.initialize()
            assert qmd._initialized is True

    @pytest.mark.asyncio
    async def test_update_calls_reindex(self):
        from cortex.search.qmd import QMDSearch

        qmd = QMDSearch(Path("/tmp/vault"), "qmd")

        with patch.object(qmd, "_run", new_callable=AsyncMock, return_value="") as mock_run:
            await qmd.update()
            cmds = [call[0][0][0] for call in mock_run.call_args_list]
            assert "update" in cmds
            assert "embed" in cmds
