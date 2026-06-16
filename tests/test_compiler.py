"""Tests for the knowledge compiler."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_chat_response(text: str) -> MagicMock:
    """Create a mock OpenAI-compatible chat completion response."""
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


class TestPrompts:
    def test_compile_prompt_exists(self):
        from cortex.compiler.prompts import COMPILE_SYSTEM_PROMPT

        assert "wiki" in COMPILE_SYSTEM_PROMPT.lower()
        assert "cross-reference" in COMPILE_SYSTEM_PROMPT.lower() or "contradiction" in COMPILE_SYSTEM_PROMPT.lower()

    def test_enrich_prompt_exists(self):
        from cortex.compiler.prompts import ENRICH_SYSTEM_PROMPT

        assert "wikilink" in ENRICH_SYSTEM_PROMPT.lower() or "[[" in ENRICH_SYSTEM_PROMPT
        assert "tag" in ENRICH_SYSTEM_PROMPT.lower()


class TestBuildIndexContext:
    @pytest.mark.asyncio
    async def test_build_index_context_with_articles(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler
        from cortex.vault.index import rebuild_index

        # Context now reads the materialized .cortex/index.md, so build it first.
        await rebuild_index(tmp_vault)
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


class TestMarkItDownIngest:
    """Tests for MarkItDown-based file conversion in ingest_source."""

    @pytest.mark.asyncio
    async def test_ingest_converts_txt_to_wiki_md(self, tmp_vault: Path):
        """ingest_source should convert a raw .txt file to a wiki markdown note
        using MarkItDown (no LLM call) and write it under wiki/."""
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        result = await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")

        assert len(result) == 1
        created = result[0]
        assert created.parent == tmp_vault / "wiki"
        assert created.suffix == ".md"
        assert created.exists()

        content = created.read_text()
        assert "Attention Is All You Need" in content

    @pytest.mark.asyncio
    async def test_ingest_adds_source_path_frontmatter(self, tmp_vault: Path):
        """The created wiki note should have source_path in its frontmatter."""
        import frontmatter as fm
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        result = await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")
        post = fm.load(str(result[0]))
        assert post.metadata["source_path"] == "raw/transformer-paper.txt"

    @pytest.mark.asyncio
    async def test_ingest_title_from_heading(self, tmp_vault: Path):
        """Title should be extracted from the first markdown heading in content."""
        import frontmatter as fm
        from cortex.compiler.compiler import KnowledgeCompiler

        (tmp_vault / "raw" / "headed.md").write_text("# My Great Article\n\nBody here.")
        compiler = KnowledgeCompiler(tmp_vault)
        result = await compiler.ingest_source(tmp_vault / "raw" / "headed.md")
        post = fm.load(str(result[0]))
        assert post.metadata["title"] == "My Great Article"

    @pytest.mark.asyncio
    async def test_ingest_title_fallback_to_filename(self, tmp_vault: Path):
        """When no heading exists, title falls back to the filename stem."""
        import frontmatter as fm
        from cortex.compiler.compiler import KnowledgeCompiler

        (tmp_vault / "raw" / "plain-notes.txt").write_text("No heading, just text.")
        compiler = KnowledgeCompiler(tmp_vault)
        result = await compiler.ingest_source(tmp_vault / "raw" / "plain-notes.txt")
        post = fm.load(str(result[0]))
        assert post.metadata["title"] == "Plain Notes"

    @pytest.mark.asyncio
    async def test_ingest_kebab_case_filename(self, tmp_vault: Path):
        """Output filename should be kebab-case derived from the source stem."""
        from cortex.compiler.compiler import KnowledgeCompiler

        (tmp_vault / "raw" / "My Research Paper.txt").write_text("Content here.")
        compiler = KnowledgeCompiler(tmp_vault)
        result = await compiler.ingest_source(tmp_vault / "raw" / "My Research Paper.txt")
        assert result[0].name == "my-research-paper.md"

    @pytest.mark.asyncio
    async def test_ingest_appends_daily_log_entry(self, tmp_vault: Path):
        """Each compile via ingest_source appends a `compile` entry to daily/<UTC-date>.md."""
        from datetime import datetime, timezone
        from cortex.compiler.compiler import KnowledgeCompiler

        fixed = datetime(2026, 6, 10, 15, 45, tzinfo=timezone.utc)
        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.vault.daily_log._utc_now", return_value=fixed):
            await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")

        daily_path = tmp_vault / "daily" / "2026-06-10.md"
        assert daily_path.exists()
        content = daily_path.read_text(encoding="utf-8")
        assert "compile" in content
        assert "[[transformer-paper]]" in content

    @pytest.mark.asyncio
    async def test_ingest_nested_raw_preserves_subdirs(self, tmp_vault: Path):
        """Nested raw paths map to mirrored wiki paths with kebab-case stems."""
        from cortex.compiler.compiler import KnowledgeCompiler

        nested = tmp_vault / "raw" / "abcde" / "docs"
        nested.mkdir(parents=True)
        (nested / "Cap Order.html").write_text("<html><body><h1>Cap</h1></body></html>")
        compiler = KnowledgeCompiler(tmp_vault)
        result = await compiler.ingest_source(nested / "Cap Order.html")
        assert result[0] == tmp_vault / "wiki" / "abcde" / "docs" / "cap-order.md"
        assert result[0].exists()


class TestLLMEnrichment:
    """Tests for the LLM enrichment step that adds wikilinks and tags after MarkItDown conversion."""

    @pytest.mark.asyncio
    async def test_enrich_adds_wikilinks_and_tags(self, tmp_vault: Path):
        """After MarkItDown conversion, enrich_article should call LLM to add wikilinks and tags."""
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        enriched_json = json.dumps({
            "content": "# Transformers\n\nThe [[transformer-architecture]] uses [[attention-mechanisms]].",
            "tags": ["ml", "architecture", "nlp"],
        })
        mock_response = _mock_chat_response(enriched_json)

        with patch.object(
            compiler.client.chat.completions, "create",
            new_callable=AsyncMock, return_value=mock_response,
        ):
            result = await compiler.enrich_article(
                "# Transformers\n\nThe transformer architecture uses attention mechanisms.",
                "Transformers",
            )
        assert "[[" in result["content"]
        assert len(result["tags"]) > 0

    @pytest.mark.asyncio
    async def test_enrich_gracefully_handles_bad_llm_response(self, tmp_vault: Path):
        """If LLM returns invalid JSON, enrich should return original content with no tags."""
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)
        mock_response = _mock_chat_response("not valid json at all")

        original = "# Test\n\nPlain content."
        with patch.object(
            compiler.client.chat.completions, "create",
            new_callable=AsyncMock, return_value=mock_response,
        ):
            result = await compiler.enrich_article(original, "Test")
        assert result["content"] == original
        assert result["tags"] == []

    @pytest.mark.asyncio
    async def test_ingest_source_calls_enrich(self, tmp_vault: Path):
        """ingest_source should call enrich_article and write the enriched content."""
        import frontmatter as fm
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        enriched_json = json.dumps({
            "content": "# Attention Is All You Need\n\nIntroduces the [[transformer-architecture]].",
            "tags": ["ml", "attention"],
        })
        mock_response = _mock_chat_response(enriched_json)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = "test-key"
            mock_settings.compiler_max_file_size_mb = 50
            with patch.object(
                compiler.client.chat.completions, "create",
                new_callable=AsyncMock, return_value=mock_response,
            ):
                result = await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")

        post = fm.load(str(result[0]))
        assert "[[transformer-architecture]]" in post.content
        assert "ml" in post.metadata.get("tags", [])

    @pytest.mark.asyncio
    async def test_ingest_skips_enrich_when_no_api_key(self, tmp_vault: Path):
        """When LLM API key is not set, ingest should skip enrichment gracefully."""
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.llm_base_url = "https://openrouter.ai/api/v1"
            mock_settings.compiler_model = "test"
            mock_settings.compiler_max_tokens = 4096
            mock_settings.compiler_max_file_size_mb = 50
            result = await compiler.ingest_source(tmp_vault / "raw" / "transformer-paper.txt")

        assert len(result) == 1
        assert result[0].exists()


class TestEnrichmentStatus:
    """Tests that ingest_source records enrichment quality in frontmatter."""

    @pytest.mark.asyncio
    async def test_successful_enrichment_marked_complete(self, tmp_vault: Path):
        """When LLM returns wikilinks and tags, enrichment_status should be 'complete'."""
        import frontmatter as fm
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)
        enriched_json = json.dumps({
            "content": "# Paper\n\nUses [[attention-mechanisms]] for NLP.",
            "tags": ["ml", "nlp"],
        })
        mock_response = _mock_chat_response(enriched_json)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = "test-key"
            mock_settings.llm_base_url = "https://test"
            mock_settings.compiler_model = "test"
            mock_settings.compiler_max_tokens = 4096
            mock_settings.compiler_max_file_size_mb = 50
            with patch.object(
                compiler.client.chat.completions, "create",
                new_callable=AsyncMock, return_value=mock_response,
            ):
                result = await compiler.ingest_source(
                    tmp_vault / "raw" / "transformer-paper.txt"
                )

        post = fm.load(str(result[0]))
        assert post.metadata.get("enrichment_status") == "complete"

    @pytest.mark.asyncio
    async def test_failed_enrichment_marked_incomplete(self, tmp_vault: Path):
        """When LLM returns no tags and no wikilinks, enrichment_status should be 'incomplete'."""
        import frontmatter as fm
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)
        mock_response = _mock_chat_response("not valid json")

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = "test-key"
            mock_settings.llm_base_url = "https://test"
            mock_settings.compiler_model = "test"
            mock_settings.compiler_max_tokens = 4096
            mock_settings.compiler_max_file_size_mb = 50
            with patch.object(
                compiler.client.chat.completions, "create",
                new_callable=AsyncMock, return_value=mock_response,
            ):
                result = await compiler.ingest_source(
                    tmp_vault / "raw" / "transformer-paper.txt"
                )

        post = fm.load(str(result[0]))
        assert post.metadata.get("enrichment_status") == "incomplete"

    @pytest.mark.asyncio
    async def test_no_llm_key_marked_incomplete(self, tmp_vault: Path):
        """When no LLM API key is set, enrichment_status should be 'incomplete'."""
        import frontmatter as fm
        from cortex.compiler.compiler import KnowledgeCompiler

        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.llm_base_url = "https://test"
            mock_settings.compiler_model = "test"
            mock_settings.compiler_max_tokens = 4096
            mock_settings.compiler_max_file_size_mb = 50
            result = await compiler.ingest_source(
                tmp_vault / "raw" / "transformer-paper.txt"
            )

        post = fm.load(str(result[0]))
        assert post.metadata.get("enrichment_status") == "incomplete"


class TestIngestSkipManifest:
    """ingest_source records compiler-level skip reasons in the skip manifest."""

    @pytest.mark.asyncio
    async def test_file_too_large_recorded(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler
        from cortex.compiler.ingest_manifest import load_skip_manifest

        large_file = tmp_vault / "raw" / "huge.txt"
        large_file.write_bytes(b"x" * 1024)
        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.compiler_max_file_size_mb = 0
            result = await compiler.ingest_source(large_file)

        assert result == []
        manifest = load_skip_manifest(tmp_vault)
        assert "raw/huge.txt" in manifest
        assert manifest["raw/huge.txt"]["reason"].startswith("file too large")

    @pytest.mark.asyncio
    async def test_wiki_up_to_date_recorded(self, tmp_vault: Path):
        import os
        import time

        from cortex.compiler.compiler import KnowledgeCompiler
        from cortex.compiler.ingest_manifest import load_skip_manifest

        raw_file = tmp_vault / "raw" / "transformer-paper.txt"
        wiki_file = tmp_vault / "wiki" / "transformer-paper.md"
        wiki_file.parent.mkdir(parents=True, exist_ok=True)
        raw_file.write_text("raw content")
        wiki_file.write_text("# Existing\n")
        now = time.time()
        os.utime(raw_file, (now - 10, now - 10))
        os.utime(wiki_file, (now, now))

        compiler = KnowledgeCompiler(tmp_vault)
        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.compiler_max_file_size_mb = 50
            result = await compiler.ingest_source(raw_file)

        assert result == [wiki_file]
        manifest = load_skip_manifest(tmp_vault)
        assert manifest["raw/transformer-paper.txt"]["reason"] == "wiki already up-to-date"

    @pytest.mark.asyncio
    async def test_empty_conversion_recorded(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler
        from cortex.compiler.ingest_manifest import load_skip_manifest

        raw_file = tmp_vault / "raw" / "empty.txt"
        raw_file.write_text("content")
        compiler = KnowledgeCompiler(tmp_vault)

        empty_result = MagicMock()
        empty_result.text_content = "   "

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.compiler_max_file_size_mb = 50
            mock_settings.llm_api_key = ""
            with patch.object(compiler._md, "convert_local", return_value=empty_result):
                result = await compiler.ingest_source(raw_file)

        assert result == []
        manifest = load_skip_manifest(tmp_vault)
        assert manifest["raw/empty.txt"]["reason"] == "empty conversion result"

    @pytest.mark.asyncio
    async def test_conversion_failure_recorded(self, tmp_vault: Path):
        from cortex.compiler.compiler import KnowledgeCompiler
        from cortex.compiler.ingest_manifest import load_skip_manifest

        raw_file = tmp_vault / "raw" / "broken.txt"
        raw_file.write_text("content")
        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.compiler_max_file_size_mb = 50
            with patch.object(
                compiler._md,
                "convert_local",
                side_effect=RuntimeError("unsupported format"),
            ):
                result = await compiler.ingest_source(raw_file)

        assert result == []
        manifest = load_skip_manifest(tmp_vault)
        assert manifest["raw/broken.txt"]["reason"] == "conversion failed: unsupported format"


class TestTitleAndSlugHelpers:
    """Unit tests for slug_from_stem and _title_from_markdown helpers."""

    def test_slug_from_stem_simple(self):
        from cortex.vault.layout import slug_from_stem
        assert slug_from_stem("transformer-paper") == "transformer-paper"

    def test_slug_from_stem_spaces(self):
        from cortex.vault.layout import slug_from_stem
        assert slug_from_stem("My Research Paper") == "my-research-paper"

    def test_slug_from_stem_special_chars(self):
        from cortex.vault.layout import slug_from_stem
        assert slug_from_stem("file (1) [copy]") == "file-1-copy"

    def test_title_from_markdown_h1(self):
        from cortex.compiler.compiler import _title_from_markdown
        assert _title_from_markdown("# Hello World\nBody", "fallback") == "Hello World"

    def test_title_from_markdown_h2(self):
        from cortex.compiler.compiler import _title_from_markdown
        assert _title_from_markdown("## Sub Heading\nBody", "fallback") == "Sub Heading"

    def test_title_from_markdown_no_heading(self):
        from cortex.compiler.compiler import _title_from_markdown
        assert _title_from_markdown("Just text", "my-file") == "My File"


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

    def test_detect_source_type_docx(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("report.docx")) == "docx"

    def test_detect_source_type_html(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("page.html")) == "html"

    def test_detect_source_type_csv(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("data.csv")) == "csv"

    def test_detect_source_type_unknown(self):
        from cortex.compiler.extractor import detect_source_type

        assert detect_source_type(Path("data.bin")) == "text"

    def test_extract_text_from_txt(self, tmp_path: Path):
        from cortex.compiler.extractor import extract_text

        txt_file = tmp_path / "sample.txt"
        txt_file.write_text("Hello, this is a test document.")
        result = extract_text(txt_file)
        assert "Hello, this is a test document." in result

    def test_extract_text_from_html(self, tmp_path: Path):
        from cortex.compiler.extractor import extract_text

        html_file = tmp_path / "page.html"
        html_file.write_text("<html><body><h1>Title</h1><p>Paragraph.</p></body></html>")
        result = extract_text(html_file)
        assert "Title" in result
        assert "Paragraph" in result
