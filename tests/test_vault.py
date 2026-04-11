from __future__ import annotations

from pathlib import Path

import pytest


class TestExtractWikilinks:
    def test_single_wikilink(self):
        from cortex.vault.reader import extract_wikilinks

        result = extract_wikilinks("See [[transformers]] for details.")
        assert result == ["transformers"]

    def test_multiple_wikilinks(self):
        from cortex.vault.reader import extract_wikilinks

        result = extract_wikilinks("See [[transformers]] and [[attention-mechanisms]].")
        assert result == ["transformers", "attention-mechanisms"]

    def test_aliased_wikilink(self):
        from cortex.vault.reader import extract_wikilinks

        result = extract_wikilinks("See [[transformers|the transformer paper]].")
        assert result == ["transformers"]

    def test_no_wikilinks(self):
        from cortex.vault.reader import extract_wikilinks

        result = extract_wikilinks("No links here.")
        assert result == []

    def test_wikilinks_with_special_chars(self):
        from cortex.vault.reader import extract_wikilinks

        result = extract_wikilinks("[[rnn-claims]] and [[multi word note]]")
        assert result == ["rnn-claims", "multi word note"]


class TestInferNodeType:
    def test_raw_source(self):
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("raw/paper.txt", {}) == NodeType.RAW_SOURCE

    def test_agent_def(self):
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("agents/scout.agent.md", {}) == NodeType.AGENT_DEF

    def test_memory(self):
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("memories/ctx.memory.md", {}) == NodeType.MEMORY

    def test_session(self):
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("sessions/2026-04-11.session.md", {}) == NodeType.SESSION

    def test_frontmatter_type_override(self):
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("wiki/test.md", {"type": "agent_def"}) == NodeType.AGENT_DEF

    def test_default_note(self):
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("wiki/transformers.md", {}) == NodeType.NOTE


class TestReadNote:
    def test_read_wiki_note(self, tmp_vault: Path):
        from cortex.vault.reader import read_note
        from cortex.vault.models import NodeType

        note = read_note(tmp_vault / "wiki" / "transformers.md", tmp_vault)
        assert note.title == "Transformer Architecture"
        assert note.node_type == NodeType.NOTE
        assert "attention-mechanisms" in note.wikilinks
        assert "rnn-claims" in note.wikilinks
        assert "ml" in note.tags
        assert "architecture" in note.tags
        assert note.provenance.authored_by == "claude-sonnet-4"
        assert note.path == "wiki/transformers.md"

    def test_read_agent_note(self, tmp_vault: Path):
        from cortex.vault.reader import read_note
        from cortex.vault.models import NodeType

        note = read_note(tmp_vault / "agents" / "research-scout.agent.md", tmp_vault)
        assert note.node_type == NodeType.AGENT_DEF
        assert note.title == "Research Scout"

    def test_title_from_heading(self, tmp_vault: Path):
        """If no title in frontmatter, extract from first # heading."""
        (tmp_vault / "wiki" / "no-title.md").write_text(
            "---\ntags: [test]\n---\n\n# My Heading\n\nContent.\n"
        )
        from cortex.vault.reader import read_note

        note = read_note(tmp_vault / "wiki" / "no-title.md", tmp_vault)
        assert note.title == "My Heading"

    def test_title_from_filename(self, tmp_vault: Path):
        """If no title and no heading, use filename stem."""
        (tmp_vault / "wiki" / "fallback-title.md").write_text(
            "---\ntags: [test]\n---\n\nJust content.\n"
        )
        from cortex.vault.reader import read_note

        note = read_note(tmp_vault / "wiki" / "fallback-title.md", tmp_vault)
        assert note.title == "fallback-title"

    def test_read_nonexistent_raises(self, tmp_vault: Path):
        from cortex.vault.reader import read_note

        with pytest.raises(FileNotFoundError):
            read_note(tmp_vault / "wiki" / "nonexistent.md", tmp_vault)


class TestScanVault:
    def test_scan_finds_all_notes(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault

        notes = scan_vault(tmp_vault)
        paths = [n.path for n in notes]
        assert "wiki/transformers.md" in paths
        assert "wiki/attention-mechanisms.md" in paths
        assert "agents/research-scout.agent.md" in paths
        assert "sessions/2026-04-11.session.md" in paths

    def test_scan_skips_cortex_dir(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault

        notes = scan_vault(tmp_vault)
        paths = [n.path for n in notes]
        for p in paths:
            assert not p.startswith(".cortex/")


class TestResolveWikilink:
    def test_resolve_existing(self, tmp_vault: Path):
        from cortex.vault.reader import resolve_wikilink

        result = resolve_wikilink("transformers", tmp_vault)
        assert result == "wiki/transformers.md"

    def test_resolve_nonexistent(self, tmp_vault: Path):
        from cortex.vault.reader import resolve_wikilink

        result = resolve_wikilink("nonexistent-note", tmp_vault)
        assert result is None

    def test_resolve_agent(self, tmp_vault: Path):
        from cortex.vault.reader import resolve_wikilink

        result = resolve_wikilink("research-scout.agent", tmp_vault)
        assert result == "agents/research-scout.agent.md"
