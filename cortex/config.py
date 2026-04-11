from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class CortexSettings(BaseSettings):
    vault_path: Path = Path("./vault")

    qmd_bin: str = "qmd"
    qmd_url: str = ""

    anthropic_api_key: str = ""
    compiler_model: str = "claude-sonnet-4-20250514"
    compiler_max_tokens: int = 4096

    mcp_transport: str = "stdio"
    mcp_sse_host: str = "0.0.0.0"
    mcp_sse_port: int = 8420

    max_context_depth: int = 2
    max_context_notes: int = 8

    default_author: str = "human"

    model_config = {"env_prefix": "CORTEX_"}


settings = CortexSettings()
