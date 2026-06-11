"""Validate docker-compose.yml wiring (volumes, env pass-through)."""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_cortex_service_has_ingest_volume():
    """The cortex service must have an optional INGEST_DIR volume mount."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    data = yaml.safe_load(compose_path.read_text())

    cortex_volumes = data["services"]["cortex"]["volumes"]
    ingest_mount = [v for v in cortex_volumes if "/ingest" in v]
    assert ingest_mount, "Expected an /ingest volume mount on the cortex service"
    assert ingest_mount[0].endswith(":/ingest:ro")


def test_cortex_service_passes_qmd_cache_ttl():
    """QMD_CACHE_TTL_SECONDS from .env must reach the container as CORTEX_QMD_CACHE_TTL_SECONDS."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    data = yaml.safe_load(compose_path.read_text())

    env = data["services"]["cortex"]["environment"]
    ttl = [e for e in env if e.startswith("CORTEX_QMD_CACHE_TTL_SECONDS=")]
    assert ttl, "Expected CORTEX_QMD_CACHE_TTL_SECONDS in cortex environment"
    assert "${QMD_CACHE_TTL_SECONDS:-30}" in ttl[0]


def test_env_check_persists_qmd_cache_ttl():
    """write_env_file in env_check.sh must preserve QMD_CACHE_TTL_SECONDS across regens."""
    content = (REPO_ROOT / "scripts" / "env_check.sh").read_text()
    assert "QMD_CACHE_TTL_SECONDS=${QMD_CACHE_TTL_SECONDS" in content, (
        "start.sh regenerates .env; without QMD_CACHE_TTL_SECONDS in "
        "write_env_file a user-set TTL is silently dropped on next start"
    )


def test_cortex_service_passes_qmd_search_mode_and_timeout():
    """Search mode and timeout must reach the container so Docker users can tune them."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    env = yaml.safe_load(compose_path.read_text())["services"]["cortex"]["environment"]

    mode = [e for e in env if e.startswith("CORTEX_QMD_SEARCH_MODE=")]
    timeout = [e for e in env if e.startswith("CORTEX_QMD_SEARCH_TIMEOUT_SECONDS=")]
    assert mode, "Expected CORTEX_QMD_SEARCH_MODE in cortex environment"
    assert "${QMD_SEARCH_MODE:-hybrid}" in mode[0]
    assert timeout, "Expected CORTEX_QMD_SEARCH_TIMEOUT_SECONDS in cortex environment"
    assert "${QMD_SEARCH_TIMEOUT_SECONDS:-120}" in timeout[0]


def test_env_check_persists_search_mode_and_timeout():
    """env_check.sh must persist the search-mode/timeout knobs across .env regens."""
    content = (REPO_ROOT / "scripts" / "env_check.sh").read_text()
    assert "QMD_SEARCH_MODE=${QMD_SEARCH_MODE" in content
    assert "QMD_SEARCH_TIMEOUT_SECONDS=${QMD_SEARCH_TIMEOUT_SECONDS" in content


def test_env_example_documents_qmd_cache_ttl():
    """.env.example must document the QMD cache TTL knob."""
    content = (REPO_ROOT / ".env.example").read_text()
    assert "QMD_CACHE_TTL_SECONDS" in content
