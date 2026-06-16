"""Tests for vault reader and scanner."""
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

    def test_infer_feedback_node_type(self):
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("feedback/2026-05-28T16-45-00.md", {}) == NodeType.FEEDBACK
        assert infer_node_type("feedback/x.md", {"type": "feedback"}) == NodeType.FEEDBACK

    def test_agent_def_by_folder_without_suffix(self):
        """Files under `agents/` are AGENT_DEF even without `.agent.md` suffix."""
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("agents/research-scout.md", {}) == NodeType.AGENT_DEF

    def test_session_by_folder_without_suffix(self):
        """Files under `sessions/` are SESSION even without `.session.md` suffix."""
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("sessions/2026-06-10.md", {}) == NodeType.SESSION

    def test_daily_by_folder(self):
        """Files under `daily/` are classified as DAILY (Obsidian daily-notes convention)."""
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("daily/2026-06-10.md", {}) == NodeType.DAILY

    def test_agent_suffix_outside_agents_folder_still_works(self):
        """Backward-compat: `.agent.md` suffix outside `agents/` still maps to AGENT_DEF."""
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("wiki/legacy-scout.agent.md", {}) == NodeType.AGENT_DEF

    def test_session_suffix_outside_sessions_folder_still_works(self):
        """Backward-compat: `.session.md` suffix outside `sessions/` still maps to SESSION."""
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("wiki/legacy.session.md", {}) == NodeType.SESSION

    def test_frontmatter_type_overrides_folder(self):
        """Explicit `type:` in frontmatter wins over any folder-based inference."""
        from cortex.vault.reader import infer_node_type
        from cortex.vault.models import NodeType

        assert infer_node_type("agents/foo.md", {"type": "note"}) == NodeType.NOTE
        assert infer_node_type("daily/foo.md", {"type": "note"}) == NodeType.NOTE
        assert infer_node_type("sessions/foo.md", {"type": "feedback"}) == NodeType.FEEDBACK


class TestNormalizeTags:
    def test_flat_list(self):
        from cortex.vault.reader import normalize_tags

        assert normalize_tags(["ml", "architecture"]) == ["ml", "architecture"]

    def test_comma_separated_string(self):
        from cortex.vault.reader import normalize_tags

        assert normalize_tags("ml, architecture, nlp") == ["ml", "architecture", "nlp"]

    def test_nested_list(self):
        from cortex.vault.reader import normalize_tags

        assert normalize_tags([["avaloq", "configuration"], "import"]) == [
            "avaloq",
            "configuration",
            "import",
        ]

    def test_empty_and_none(self):
        from cortex.vault.reader import normalize_tags

        assert normalize_tags([]) == []
        assert normalize_tags(None) == []

    def test_joinable(self):
        from cortex.vault.reader import normalize_tags

        tags = normalize_tags([["avaloq", "configuration"]])
        assert ", ".join(tags) == "avaloq, configuration"


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

    def test_read_directory_raises(self, tmp_vault: Path):
        """read_note must raise IsADirectoryError when path is a directory."""
        from cortex.vault.reader import read_note

        with pytest.raises(IsADirectoryError):
            read_note(tmp_vault / "wiki", tmp_vault)

    def test_read_non_markdown_raises(self, tmp_vault: Path):
        from cortex.vault.reader import read_note

        pdf = tmp_vault / "raw" / "sample.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4 fake")

        with pytest.raises(ValueError, match="not a markdown note"):
            read_note(pdf, tmp_vault)

    def test_read_note_normalizes_nested_tags(self, tmp_vault: Path):
        path = tmp_vault / "wiki" / "nested-tags.md"
        path.write_text(
            "---\n"
            "title: Nested Tags\n"
            "tags:\n"
            "  - - avaloq\n"
            "    - configuration\n"
            "  - import\n"
            "---\n\n"
            "# Nested Tags\n"
        )
        from cortex.vault.reader import read_note

        note = read_note(path, tmp_vault)
        assert note.tags == ["avaloq", "configuration", "import"]
        assert ", ".join(note.tags) == "avaloq, configuration, import"


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

    def test_scan_assigns_node_types_by_folder(self, tmp_vault: Path):
        """Unsuffixed files under agents/, sessions/, daily/ scan with correct NodeType."""
        from cortex.vault.reader import scan_vault
        from cortex.vault.models import NodeType

        (tmp_vault / "agents" / "planner.md").write_text(
            "---\ntitle: Planner Agent\n---\n\n# Planner\n"
        )
        (tmp_vault / "sessions" / "2026-06-10.md").write_text(
            "---\ntitle: Daily standup\n---\n\n# Standup\n"
        )
        (tmp_vault / "daily" / "2026-06-10.md").write_text(
            "---\ntitle: 2026-06-10\n---\n\n# 2026-06-10\n"
        )

        notes = scan_vault(tmp_vault)
        by_path = {n.path: n for n in notes}

        assert by_path["agents/planner.md"].node_type == NodeType.AGENT_DEF
        assert by_path["sessions/2026-06-10.md"].node_type == NodeType.SESSION
        assert by_path["daily/2026-06-10.md"].node_type == NodeType.DAILY


class TestScanVaultAsync:
    @pytest.mark.asyncio
    async def test_returns_same_results_as_sync(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault, scan_vault_async

        sync_notes = scan_vault(tmp_vault)
        async_notes = await scan_vault_async(tmp_vault)

        sync_paths = sorted(n.path for n in sync_notes)
        async_paths = sorted(n.path for n in async_notes)
        assert sync_paths == async_paths

    @pytest.mark.asyncio
    async def test_finds_all_notes(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault_async

        notes = await scan_vault_async(tmp_vault)
        paths = [n.path for n in notes]
        assert "wiki/transformers.md" in paths
        assert "wiki/attention-mechanisms.md" in paths

    @pytest.mark.asyncio
    async def test_skips_cortex_dir(self, tmp_vault: Path):
        from cortex.vault.reader import scan_vault_async

        notes = await scan_vault_async(tmp_vault)
        for n in notes:
            assert not n.path.startswith(".cortex/")


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


class TestBuildWikilinkIndex:
    def test_returns_dict(self, tmp_vault: Path):
        from cortex.vault.reader import build_wikilink_index

        index = build_wikilink_index(tmp_vault)
        assert isinstance(index, dict)
        assert "transformers" in index
        assert index["transformers"] == "wiki/transformers.md"

    def test_covers_all_stems(self, tmp_vault: Path):
        from cortex.vault.reader import build_wikilink_index

        index = build_wikilink_index(tmp_vault)
        assert "attention-mechanisms" in index
        assert "research-scout.agent" in index

    def test_skips_cortex_dir(self, tmp_vault: Path):
        from cortex.vault.reader import build_wikilink_index

        index = build_wikilink_index(tmp_vault)
        for _stem, path in index.items():
            assert not path.startswith(".cortex/")

    def test_resolve_with_index_matches_filesystem(self, tmp_vault: Path):
        from cortex.vault.reader import build_wikilink_index, resolve_wikilink

        index = build_wikilink_index(tmp_vault)
        assert index.get("transformers") == resolve_wikilink("transformers", tmp_vault)
        assert index.get("nonexistent") is None
