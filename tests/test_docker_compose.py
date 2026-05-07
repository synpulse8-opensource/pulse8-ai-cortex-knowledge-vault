"""Validate docker-compose.yml contains the INGEST_DIR volume mount."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_cortex_service_has_ingest_volume():
    """The cortex service must have an optional INGEST_DIR volume mount."""
    compose_path = Path(__file__).resolve().parent.parent / "docker-compose.yml"
    data = yaml.safe_load(compose_path.read_text())

    cortex_volumes = data["services"]["cortex"]["volumes"]
    ingest_mount = [v for v in cortex_volumes if "/ingest" in v]
    assert ingest_mount, "Expected an /ingest volume mount on the cortex service"
    assert ingest_mount[0].endswith(":/ingest:ro")
