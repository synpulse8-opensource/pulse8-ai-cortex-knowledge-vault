"""Tests for configurable vault raw/wiki directory names."""
from __future__ import annotations

from pathlib import Path


def test_vault_dir_defaults():
    from cortex.config import CortexSettings

    s = CortexSettings()
    assert s.vault_raw_dir == "raw"
    assert s.vault_wiki_dir == "wiki"


def test_vault_dirs_from_env(monkeypatch):
    monkeypatch.setenv("CORTEX_VAULT_RAW_DIR", "raw2")
    monkeypatch.setenv("CORTEX_VAULT_WIKI_DIR", "wiki2")

    from cortex.config import CortexSettings

    s = CortexSettings()
    assert s.vault_raw_dir == "raw2"
    assert s.vault_wiki_dir == "wiki2"


def test_layout_paths(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CORTEX_VAULT_RAW_DIR", "raw3")
    monkeypatch.setenv("CORTEX_VAULT_WIKI_DIR", "wiki3")

    from cortex.config import CortexSettings
    from cortex.vault import layout

    monkeypatch.setattr("cortex.vault.layout.settings", CortexSettings())

    vault = tmp_path / "vault"
    vault.mkdir()
    assert layout.raw_dir(vault) == vault / "raw3"
    assert layout.wiki_dir(vault) == vault / "wiki3"
    assert layout.raw_rel("paper.pdf") == "raw3/paper.pdf"
    assert layout.is_raw_path("raw3/paper.pdf")
    assert layout.wikilink_search_dirs()[0] == "wiki3"


def test_infer_node_type_uses_configured_raw(monkeypatch):
    from cortex.config import CortexSettings

    monkeypatch.setenv("CORTEX_VAULT_RAW_DIR", "raw1")
    monkeypatch.setattr("cortex.vault.layout.settings", CortexSettings())

    from cortex.vault.models import NodeType
    from cortex.vault.reader import infer_node_type

    assert infer_node_type("raw1/source.txt", {}) == NodeType.RAW_SOURCE


def test_slug_from_stem():
    from cortex.vault.layout import slug_from_stem

    assert slug_from_stem("My Report") == "my-report"
    assert slug_from_stem("report") == "report"


def test_wiki_dest_for_raw_flat(tmp_path: Path):
    from cortex.vault.layout import wiki_dest_for_raw

    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    raw = vault / "raw" / "My Paper.html"
    assert wiki_dest_for_raw(vault, raw) == vault / "wiki" / "my-paper.md"


def test_wiki_dest_for_raw_nested(tmp_path: Path):
    from cortex.vault.layout import wiki_dest_for_raw

    vault = tmp_path / "vault"
    nested = vault / "raw" / "abcde"
    nested.mkdir(parents=True)
    raw = nested / "report.html"
    assert wiki_dest_for_raw(vault, raw) == vault / "wiki" / "abcde" / "report.md"


def test_wiki_dest_for_raw_nested_kebab_stem(tmp_path: Path):
    from cortex.vault.layout import wiki_dest_for_raw

    vault = tmp_path / "vault"
    nested = vault / "raw" / "abcde" / "docs"
    nested.mkdir(parents=True)
    raw = nested / "Cap Order.html"
    assert wiki_dest_for_raw(vault, raw) == vault / "wiki" / "abcde" / "docs" / "cap-order.md"
