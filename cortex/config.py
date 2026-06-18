"""Cortex application settings via pydantic-settings."""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class CortexSettings(BaseSettings):
    """Cortex configuration loaded from environment variables with CORTEX_ prefix."""
    vault_path: Path = Path("./vault")
    vault_raw_dir: str = "raw"
    vault_wiki_dir: str = "wiki"

    qmd_bin: str = "qmd"
    qmd_url: str = ""
    qmd_search_mode: str = "hybrid"

    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    compiler_model: str = "qwen/qwen3.5-flash-02-23" # "google/gemini-2.5-flash"
    compiler_max_tokens: int = 4096
    compiler_max_file_size_mb: int = 50

    qmd_refresh_interval_seconds: int = 900
    qmd_cache_ttl_seconds: float = 30.0
    # Hybrid search on CPU-only hosts can take minutes (query expansion +
    # embed + rerank); 30s silently truncated those searches to [].
    qmd_search_timeout_seconds: float = 120.0

    mcp_transport: str = "stdio"
    mcp_sse_host: str = "0.0.0.0"
    mcp_sse_port: int = 8420
    mcp_allowed_hosts: str = "*"

    max_context_depth: int = 2
    max_context_notes: int = 8

    default_author: str = "human"

    auth_method: str = "none"

    api_key: str = ""

    oidc_tenant_id: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_base_url: str = ""

    teams_webhook_url: str = ""
    teams_app_base_url: str = ""

    # MCP resource store (resources-as-tool-inputs pattern). TTL is the
    # max age of a stored payload; max_items caps the in-memory dict
    # before LRU eviction kicks in.
    resource_ttl_seconds: int = 3600
    resource_max_items: int = 1000

    @field_validator("vault_raw_dir", "vault_wiki_dir")
    @classmethod
    def _validate_vault_dir_name(cls, value: str) -> str:
        name = value.strip().strip("/")
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError("vault folder names must be a single path segment")
        return name

    @property
    def auth_enabled(self) -> bool:
        """True when any authentication method is active."""
        return self.auth_method in ("apikey", "oidc")

    @property
    def auth_is_apikey(self) -> bool:
        return self.auth_method == "apikey"

    @property
    def auth_is_oidc(self) -> bool:
        return self.auth_method == "oidc"

    @property
    def oidc_enabled(self) -> bool:
        return self.auth_is_oidc and bool(self.oidc_tenant_id and self.oidc_client_id)

    @property
    def oidc_config_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self.oidc_tenant_id}"
            "/v2.0/.well-known/openid-configuration"
        )

    @property
    def oidc_token_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self.oidc_tenant_id}"
            "/oauth2/v2.0/token"
        )

    @property
    def oidc_authorize_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self.oidc_tenant_id}"
            "/oauth2/v2.0/authorize"
        )

    @property
    def oidc_issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.oidc_tenant_id}/v2.0"

    @property
    def oidc_redirect_uri(self) -> str:
        base = (self.oidc_base_url or f"http://localhost:{self.mcp_sse_port}").rstrip("/")
        return f"{base}/api/v1/auth/callback"

    model_config = {"env_prefix": "CORTEX_"}


settings = CortexSettings()
