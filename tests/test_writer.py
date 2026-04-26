"""Tests for note writer."""
from __future__ import annotations

from pathlib import Path

import frontmatter as fm
import pytest


class TestMergeFrontmatter:
    def test_merge_adds_new_keys(self):
        from cortex.vault.writer import merge_frontmatter

        result = merge_frontmatter({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_merge_overrides_existing(self):
        from cortex.vault.writer import merge_frontmatter

        result = merge_frontmatter({"a": 1}, {"a": 99})
        assert result == {"a": 99}

    def test_merge_preserves_unmentioned_keys(self):
        from cortex.vault.writer import merge_frontmatter

        result = merge_frontmatter({"a": 1, "b": 2}, {"b": 99})
        assert result == {"a": 1, "b": 99}

    def test_merge_empty_incoming(self):
        from cortex.vault.writer import merge_frontmatter

        result = merge_frontmatter({"a": 1}, {})
        assert result == {"a": 1}


class TestInjectProvenance:
    def test_sets_authored_by(self):
        from cortex.vault.writer import inject_provenance

        result = inject_provenance({}, "claude")
        assert result["authored_by"] == "claude"

    def test_sets_updated_at(self):
        from cortex.vault.writer import inject_provenance

        result = inject_provenance({}, "human")
        assert "updated_at" in result

    def test_sets_created_at_if_absent(self):
        from cortex.vault.writer import inject_provenance

        result = inject_provenance({}, "human")
        assert "created_at" in result

    def test_preserves_existing_created_at(self):
        from cortex.vault.writer import inject_provenance

        result = inject_provenance({"created_at": "2026-01-01T00:00:00Z"}, "human")
        assert result["created_at"] == "2026-01-01T00:00:00Z"

    def test_sets_model_if_provided(self):
        from cortex.vault.writer import inject_provenance

        result = inject_provenance({}, "claude", model="claude-sonnet-4")
        assert result["model"] == "claude-sonnet-4"

    def test_sets_confidence_if_provided(self):
        from cortex.vault.writer import inject_provenance

        result = inject_provenance({}, "claude", confidence=0.9)
        assert result["confidence"] == 0.9

    def test_no_model_key_if_not_provided(self):
        from cortex.vault.writer import inject_provenance

        result = inject_provenance({}, "human")
        assert "model" not in result


class TestWriteNote:
    def test_create_new_note(self, tmp_vault: Path):
        from cortex.vault.writer import write_note

        note = write_note(
            path=tmp_vault / "wiki" / "new-note.md",
            vault_root=tmp_vault,
            content="# New Note\n\nSome content.",
            frontmatter={"tags": ["test"]},
            mode="create",
        )
        assert note.title == "New Note"
        assert note.path == "wiki/new-note.md"
        assert (tmp_vault / "wiki" / "new-note.md").exists()

    def test_create_existing_raises(self, tmp_vault: Path):
        from cortex.vault.writer import write_note

        with pytest.raises(FileExistsError):
            write_note(
                path=tmp_vault / "wiki" / "transformers.md",
                vault_root=tmp_vault,
                content="overwrite attempt",
                mode="create",
            )

    def test_update_existing(self, tmp_vault: Path):
        from cortex.vault.writer import write_note

        note = write_note(
            path=tmp_vault / "wiki" / "transformers.md",
            vault_root=tmp_vault,
            content="# Updated Content\n\nNew body.",
            frontmatter={"tags": ["ml", "updated"]},
            mode="update",
        )
        assert note.content == "# Updated Content\n\nNew body."
        post = fm.load(str(tmp_vault / "wiki" / "transformers.md"))
        assert "updated" in post.metadata.get("tags", [])
        assert post.metadata.get("source_path") == "raw/transformer-paper.txt"

    def test_update_nonexistent_raises(self, tmp_vault: Path):
        from cortex.vault.writer import write_note

        with pytest.raises(FileNotFoundError):
            write_note(
                path=tmp_vault / "wiki" / "nonexistent.md",
                vault_root=tmp_vault,
                content="content",
                mode="update",
            )

    def test_upsert_creates_new(self, tmp_vault: Path):
        from cortex.vault.writer import write_note

        _note = write_note(
            path=tmp_vault / "wiki" / "upserted.md",
            vault_root=tmp_vault,
            content="# Upserted\n\nContent.",
            mode="upsert",
        )
        assert (tmp_vault / "wiki" / "upserted.md").exists()

    def test_upsert_updates_existing(self, tmp_vault: Path):
        from cortex.vault.writer import write_note

        note = write_note(
            path=tmp_vault / "wiki" / "transformers.md",
            vault_root=tmp_vault,
            content="# Updated via Upsert",
            mode="upsert",
        )
        assert "Updated via Upsert" in note.content

    def test_provenance_injected(self, tmp_vault: Path):
        from cortex.vault.writer import write_note

        _note = write_note(
            path=tmp_vault / "wiki" / "prov-test.md",
            vault_root=tmp_vault,
            content="# Test",
            authored_by="test-agent",
            model="test-model",
            mode="create",
        )
        post = fm.load(str(tmp_vault / "wiki" / "prov-test.md"))
        assert post.metadata["authored_by"] == "test-agent"
        assert post.metadata["model"] == "test-model"
        assert "created_at" in post.metadata

    def test_creates_parent_directories(self, tmp_vault: Path):
        from cortex.vault.writer import write_note

        _note = write_note(
            path=tmp_vault / "wiki" / "subdir" / "deep-note.md",
            vault_root=tmp_vault,
            content="# Deep",
            mode="create",
        )
        assert (tmp_vault / "wiki" / "subdir" / "deep-note.md").exists()
