"""Persistent manifests for bulk ingest dedup and skip/failure audit."""
from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from cortex.vault.layout import raw_dir, vault_rel

logger = logging.getLogger(__name__)

# ESTALE (116 on Linux): stale NFS file handle on shared vault volumes.
_STALE_ERRNOS = frozenset({getattr(errno, "ESTALE", 116), 116})
_IO_RETRIES = 5
_IO_BACKOFF_S = 0.05

_T = TypeVar("_T")

_vault_manifest_locks: dict[str, threading.Lock] = {}
_manifest_locks_guard = threading.Lock()

MANIFEST_FILENAME = "ingest-manifest.json"
MANIFEST_SKIP_FILENAME = "ingest-skip-manifest.json"


def _vault_key(vault_path: Path) -> str:
    return str(vault_path.resolve())


def _manifest_lock(vault_path: Path) -> threading.Lock:
    key = _vault_key(vault_path)
    with _manifest_locks_guard:
        lock = _vault_manifest_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _vault_manifest_locks[key] = lock
        return lock


def _is_stale_oserror(exc: OSError) -> bool:
    return exc.errno in _STALE_ERRNOS


def _retry_stale_io(path: Path, description: str, operation: Callable[[], _T]) -> _T:
    """Retry filesystem I/O when the vault is on NFS and handles go stale."""
    last: OSError | None = None
    for attempt in range(_IO_RETRIES):
        try:
            return operation()
        except OSError as exc:
            if not _is_stale_oserror(exc):
                raise
            last = exc
            logger.warning(
                "Stale file handle while %s %s (attempt %d/%d)",
                description,
                path,
                attempt + 1,
                _IO_RETRIES,
            )
            time.sleep(_IO_BACKOFF_S * (attempt + 1))
    assert last is not None
    raise last


def _load_json_file(path: Path) -> dict:
    """Load a JSON object from *path*, tolerating NFS stale handles."""

    def _read() -> dict:
        if not path.is_file():
            return {}
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {}
        return json.loads(text)

    try:
        return _retry_stale_io(path, "reading", _read)
    except OSError as exc:
        if _is_stale_oserror(exc):
            logger.warning(
                "Could not read manifest %s after retries; using empty manifest",
                path,
            )
            return {}
        raise
    except json.JSONDecodeError:
        logger.warning("Corrupt manifest %s; using empty manifest", path)
        return {}


def _atomic_write_json(path: Path, data: object) -> None:
    """Write JSON atomically so readers never see a partial file."""

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
                handle.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    _retry_stale_io(path, "writing", _write)


def manifest_path(vault_path: Path) -> Path:
    return vault_path / ".cortex" / MANIFEST_FILENAME


def skip_manifest_path(vault_path: Path) -> Path:
    return vault_path / ".cortex" / MANIFEST_SKIP_FILENAME


def hash_file(path: Path) -> str:
    """Compute SHA-256 hash of a file, returned as ``sha256:<hex>``."""

    def _hash() -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"

    return _retry_stale_io(path, "hashing", _hash)


def load_manifest(vault_path: Path) -> dict[str, str]:
    """Load the ingest manifest from disk, returning ``{}`` if missing."""
    return _load_json_file(manifest_path(vault_path))


def known_content_hashes(vault_path: Path) -> set[str]:
    """Return compiled content hashes from the manifest (locked read)."""
    with _manifest_lock(vault_path):
        return set(load_manifest(vault_path).values())


def save_manifest(vault_path: Path, manifest: dict[str, str]) -> None:
    """Persist the ingest manifest to disk."""
    with _manifest_lock(vault_path):
        _atomic_write_json(manifest_path(vault_path), manifest)


def load_skip_manifest(vault_path: Path) -> dict[str, dict[str, str]]:
    """Load the skip/failure manifest from disk, returning ``{}`` if missing."""
    return _load_json_file(skip_manifest_path(vault_path))


def save_skip_manifest(vault_path: Path, skip_manifest: dict[str, dict[str, str]]) -> None:
    """Persist the skip/failure manifest to disk."""
    with _manifest_lock(vault_path):
        _atomic_write_json(skip_manifest_path(vault_path), skip_manifest)


def record_compiled_file(vault_path: Path, raw_path: Path) -> None:
    """Record one successfully compiled raw file in the ingest manifest."""
    rel = vault_rel(vault_path, raw_path)
    logger.info("Recorded compiled file: %s", rel)
    with _manifest_lock(vault_path):
        manifest = load_manifest(vault_path)
        manifest[rel] = hash_file(raw_path)
        _atomic_write_json(manifest_path(vault_path), manifest)


def record_skipped_file(
    vault_path: Path,
    path: Path,
    reason: str,
    *,
    file_hash: str | None = None,
) -> None:
    """Record one skipped or compile-failed file in the skip manifest."""
    rel = vault_rel(vault_path, path)
    logger.info("Recorded skipped file: %s (%s)", rel, reason)
    with _manifest_lock(vault_path):
        skip_manifest = load_skip_manifest(vault_path)
        entry: dict[str, str] = {"reason": reason}
        if file_hash is None:
            hash_path = path if path.exists() else raw_dir(vault_path) / path.name
            if hash_path.exists():
                file_hash = hash_file(hash_path)
        if file_hash:
            entry["hash"] = file_hash
        skip_manifest[rel] = entry
        _atomic_write_json(skip_manifest_path(vault_path), skip_manifest)


def remove_manifest_entries(vault_path: Path, raw_rel: str) -> None:
    """Drop one raw path from both ingest manifests."""
    with _manifest_lock(vault_path):
        manifest = load_manifest(vault_path)
        skip_manifest = load_skip_manifest(vault_path)
        changed = False
        if raw_rel in manifest:
            del manifest[raw_rel]
            _atomic_write_json(manifest_path(vault_path), manifest)
            changed = True
        if raw_rel in skip_manifest:
            del skip_manifest[raw_rel]
            _atomic_write_json(skip_manifest_path(vault_path), skip_manifest)
            changed = True
        if changed:
            logger.info("Removed manifest entries for %s", raw_rel)
