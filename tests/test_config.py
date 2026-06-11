"""Tests for CortexSettings configuration."""
from __future__ import annotations

from pathlib import Path


def test_default_settings():
    """CortexSettings should have sensible defaults."""
    from cortex.config import CortexSettings

    s = CortexSettings()
    assert s.vault_path == Path("./vault")
    assert s.qmd_bin == "qmd"
    assert s.qmd_url == ""
    assert s.llm_api_key == ""
    assert s.llm_base_url == "https://openrouter.ai/api/v1"
    assert s.compiler_model == "qwen/qwen3.5-flash-02-23"
    assert s.compiler_max_tokens == 4096
    assert s.mcp_transport == "stdio"
    assert s.mcp_sse_host == "0.0.0.0"
    assert s.mcp_sse_port == 8420
    assert s.max_context_depth == 2
    assert s.max_context_notes == 8
    assert s.default_author == "human"
    assert s.qmd_search_mode == "hybrid"
    assert s.qmd_refresh_interval_seconds == 900


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


def test_qmd_url_from_env(monkeypatch):
    """CORTEX_QMD_URL should configure HTTP-based QMD client."""
    monkeypatch.setenv("CORTEX_QMD_URL", "http://qmd:3100")

    from cortex.config import CortexSettings

    s = CortexSettings()
    assert s.qmd_url == "http://qmd:3100"


def test_llm_config_from_env(monkeypatch):
    """LLM settings should be configurable via env vars."""
    monkeypatch.setenv("CORTEX_LLM_API_KEY", "sk-or-test-key")
    monkeypatch.setenv("CORTEX_LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("CORTEX_COMPILER_MODEL", "gpt-4o")

    from cortex.config import CortexSettings

    s = CortexSettings()
    assert s.llm_api_key == "sk-or-test-key"
    assert s.llm_base_url == "https://api.openai.com/v1"
    assert s.compiler_model == "gpt-4o"
