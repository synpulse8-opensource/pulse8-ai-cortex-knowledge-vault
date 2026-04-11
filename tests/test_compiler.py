from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPrompts:
    def test_ingest_prompt_exists(self):
        from cortex.compiler.prompts import INGEST_SYSTEM_PROMPT

        assert "knowledge compiler" in INGEST_SYSTEM_PROMPT.lower()
        assert "wiki" in INGEST_SYSTEM_PROMPT.lower()

    def test_compile_prompt_exists(self):
        from cortex.compiler.prompts import COMPILE_SYSTEM_PROMPT

        assert "wiki" in COMPILE_SYSTEM_PROMPT.lower()
        assert "cross-reference" in COMPILE_SYSTEM_PROMPT.lower() or "contradiction" in COMPILE_SYSTEM_PROMPT.lower()


def _mock_chat_response(text: str) -> MagicMock:
    """Create a mock OpenAI-compatible chat completion response."""
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


class TestKnowledgeCompiler:
    @pytest.mark.asyncio
    async def test_ingest_source_creates_wiki_articles(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        mock_articles = json.dumps([
            {
                "filename": "test-concept",
                "frontmatter": {"title": "Test Concept", "tags": ["test"]},
                "content": "# Test Concept\n\nSome knowledge about [[transformers]].",
            }
        ])

        mock_response = _mock_chat_response(mock_articles)

        with patch.object(compiler.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")
            assert len(result) == 1
            assert (tmp_vault / "wiki" / "test-concept.md").exists()

    @pytest.mark.asyncio
    async def test_ingest_adds_source_path(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler
        import frontmatter as fm

        compiler = KnowledgeCompiler(tmp_vault)

        mock_articles = json.dumps([
            {
                "filename": "from-paper.md",
                "frontmatter": {"title": "From Paper"},
                "content": "Content from paper.",
            }
        ])

        mock_response = _mock_chat_response(mock_articles)

        with patch.object(compiler.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")
            post = fm.load(str(tmp_vault / "wiki" / "from-paper.md"))
            assert post.metadata["source_path"] == "raw/transformer-paper.txt"

    @pytest.mark.asyncio
    async def test_ingest_handles_code_fenced_json(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        fenced = '```json\n' + json.dumps([{
            "filename": "fenced",
            "frontmatter": {"title": "Fenced"},
            "content": "Content.",
        }]) + '\n```'

        mock_response = _mock_chat_response(fenced)

        with patch.object(compiler.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_ingest_handles_invalid_llm_response(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        mock_response = _mock_chat_response("This is not valid JSON at all")

        with patch.object(compiler.client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")
            assert result == []

    def test_build_index_context_empty(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)
        context = compiler._build_index_context()
        assert "Transformer Architecture" in context

    def test_build_index_context_no_wiki(self, tmp_path: Path):
        from cortex.compiler.compiler import KnowledgeCompiler

        vault = tmp_path / "vault"
        vault.mkdir()
        compiler = KnowledgeCompiler(vault)
        context = compiler._build_index_context()
        assert context == "No existing articles."


class TestExtractor:
    def test_detect_source_type_text(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("file.txt")) == "text"

    def test_detect_source_type_pdf(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("doc.pdf")) == "pdf"

    def test_detect_source_type_markdown(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("notes.md")) == "markdown"

    def test_detect_source_type_url_file(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("link.url")) == "url"

    def test_detect_source_type_unknown(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("data.csv")) == "text"
