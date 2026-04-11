from __future__ import annotations

from pathlib import Path

import pytest


def test_default_settings():
    """CortexSettings should have sensible defaults."""
    from cortex.config import CortexSettings

    s = CortexSettings()
    assert s.vault_path == Path("./vault")
    assert s.qmd_bin == "qmd"
    assert s.anthropic_api_key == ""
    assert s.compiler_model == "claude-sonnet-4-20250514"
    assert s.compiler_max_tokens == 4096
    assert s.mcp_transport == "stdio"
    assert s.mcp_sse_host == "0.0.0.0"
    assert s.mcp_sse_port == 8420
    assert s.max_context_depth == 2
    assert s.max_context_notes == 8
    assert s.default_author == "human"


def test_settings_from_env(monkeypatch):
    """CortexSettings should read from CORTEX_ prefixed env vars."""
    monkeypatch.setenv("CORTEX_VAULT_PATH", "/tmp/test-vault")
    monkeypatch.setenv("CORTEX_MCP_TRANSPORT", "sse")
    monkeypatch.setenv("CORTEX_MCP_SSE_PORT", "9999")

    from cortex.config import CortexSettings

    s = CortexSettings()
    assert s.vault_path == Path("/tmp/test-vault")
    assert s.mcp_transport == "sse"
    assert s.mcp_sse_port == 9999
