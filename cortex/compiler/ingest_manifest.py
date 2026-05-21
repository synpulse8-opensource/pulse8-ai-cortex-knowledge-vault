"""Persistent manifests for bulk ingest dedup and skip/failure audit."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "ingest-manifest.json"
MANIFEST_SKIP_FILENAME = "ingest-skip-manifest.json"


def manifest_path(vault_path: Path) -> Path:
    return vault_path / ".cortex" / MANIFEST_FILENAME


def skip_manifest_path(vault_path: Path) -> Path:
    return vault_path / ".cortex" / MANIFEST_SKIP_FILENAME


def hash_file(path: Path) -> str:
    """Compute SHA-256 hash of a file, returned as ``sha256:<hex>``."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def load_manifest(vault_path: Path) -> dict[str, str]:
    """Load the ingest manifest from disk, returning ``{}`` if missing."""
    path = manifest_path(vault_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_manifest(vault_path: Path, manifest: dict[str, str]) -> None:
    """Persist the ingest manifest to disk."""
    path = manifest_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2))


def load_skip_manifest(vault_path: Path) -> dict[str, dict[str, str]]:
    """Load the skip/failure manifest from disk, returning ``{}`` if missing."""
    path = skip_manifest_path(vault_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_skip_manifest(vault_path: Path, skip_manifest: dict[str, dict[str, str]]) -> None:
    """Persist the skip/failure manifest to disk."""
    path = skip_manifest_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(skip_manifest, indent=2))


def record_compiled_file(vault_path: Path, raw_path: Path) -> None:
    """Record one successfully compiled raw file in the ingest manifest."""
    logger.info("Recorded compiled file: %s", raw_path.name)
    manifest = load_manifest(vault_path)
    raw_rel = f"raw/{raw_path.name}"
    manifest[raw_rel] = hash_file(raw_path)
    save_manifest(vault_path, manifest)


def record_skipped_file(
    vault_path: Path,
    path: Path,
    reason: str,
    *,
    file_hash: str | None = None,
) -> None:
    """Record one skipped or compile-failed file in the skip manifest."""
    logger.info("Recorded skipped file: %s (%s)", path.name, reason)
    skip_manifest = load_skip_manifest(vault_path)
    raw_rel = f"raw/{path.name}"
    entry: dict[str, str] = {"reason": reason}
    if file_hash is None:
        raw_file = vault_path / "raw" / path.name
        hash_path = raw_file if raw_file.exists() else path
        if hash_path.exists():
            file_hash = hash_file(hash_path)
    if file_hash:
        entry["hash"] = file_hash
    skip_manifest[raw_rel] = entry
    save_skip_manifest(vault_path, skip_manifest)
