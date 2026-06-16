"""Coordination for concurrent bulk ingest against a single vault."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

LockMode = Literal["wait", "fail"]
LockScope = Literal["vault", "source"]

BULK_INGEST_LOCK_FILENAME = "bulk-ingest.lock"

_async_locks: dict[str, asyncio.Lock] = {}
_process_locks: dict[str, threading.Lock] = {}
_process_locks_guard = threading.Lock()
_file_lock_cms: dict[str, Iterator[None]] = {}


class BulkIngestBusyError(Exception):
    """Raised when the requested bulk ingest session cannot be acquired."""

    def __init__(self, vault_path: Path, source_dir: Path | None = None) -> None:
        self.vault_path = vault_path.resolve()
        self.source_dir = source_dir.resolve() if source_dir is not None else None
        if source_dir is not None:
            msg = f"Bulk ingest already in progress for source_dir: {self.source_dir}"
        else:
            msg = f"Bulk ingest already in progress for vault: {self.vault_path}"
        super().__init__(msg)


def normalize_source_dir(source_dir: Path) -> Path:
    """Canonical path for lock keys so ``/ingest`` and ``/ingest/`` share one lock."""
    return source_dir.resolve()


def bulk_ingest_lock_path(vault_path: Path, source_dir: Path | None = None) -> Path:
    """Lock file path for vault-wide or per-source_dir bulk ingest."""
    if source_dir is None:
        return vault_path.resolve() / ".cortex" / BULK_INGEST_LOCK_FILENAME
    digest = hashlib.sha256(str(normalize_source_dir(source_dir)).encode()).hexdigest()[:16]
    return vault_path.resolve() / ".cortex" / f"bulk-ingest-{digest}.lock"


def _vault_key(vault_path: Path) -> str:
    return str(vault_path.resolve())


def _session_key(vault_path: Path, source_dir: Path | None, lock_scope: LockScope) -> str:
    if lock_scope == "vault":
        return _vault_key(vault_path)
    if source_dir is None:
        raise ValueError("source_dir is required when lock_scope='source'")
    return f"{_vault_key(vault_path)}::{normalize_source_dir(source_dir)}"


def _async_lock(session_key: str) -> asyncio.Lock:
    lock = _async_locks.get(session_key)
    if lock is None:
        lock = asyncio.Lock()
        _async_locks[session_key] = lock
    return lock


def _process_lock(session_key: str) -> threading.Lock:
    with _process_locks_guard:
        lock = _process_locks.get(session_key)
        if lock is None:
            lock = threading.Lock()
            _process_locks[session_key] = lock
        return lock


def _lock_metadata(source_dir: Path | None) -> str:
    payload = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started_at": time.time(),
        "source_dir": str(normalize_source_dir(source_dir)) if source_dir is not None else None,
    }
    return json.dumps(payload, sort_keys=True)


@contextmanager
def _file_lock_cm(
    lock_path: Path,
    vault_path: Path,
    source_dir: Path | None,
    *,
    blocking: bool,
) -> Iterator[None]:
    """Advisory flock on a vault lock file (works across pods on a shared RWX volume)."""
    try:
        import fcntl
    except ImportError:
        logger.warning(
            "fcntl unavailable — bulk ingest cross-pod lock skipped for %s",
            lock_path,
        )
        yield
        return

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as handle:
        flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        try:
            fcntl.flock(handle.fileno(), flags)
        except BlockingIOError as exc:
            raise BulkIngestBusyError(vault_path, source_dir) from exc
        handle.write(_lock_metadata(source_dir))
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _file_lock_enter(
    lock_path: Path,
    vault_path: Path,
    source_dir: Path | None,
    *,
    blocking: bool,
) -> None:
    key = str(lock_path)
    cm = _file_lock_cm(lock_path, vault_path, source_dir, blocking=blocking)
    _file_lock_cms[key] = cm
    cm.__enter__()


def _file_lock_exit(lock_path: Path) -> None:
    key = str(lock_path)
    cm = _file_lock_cms.pop(key, None)
    if cm is not None:
        cm.__exit__(None, None, None)


def _acquire_process_lock(
    session_key: str,
    vault_path: Path,
    source_dir: Path | None,
    *,
    lock_mode: LockMode,
) -> None:
    proc_lock = _process_lock(session_key)
    if lock_mode == "fail":
        if not proc_lock.acquire(blocking=False):
            raise BulkIngestBusyError(vault_path, source_dir)
    else:
        proc_lock.acquire(blocking=True)


def _release_process_lock(session_key: str) -> None:
    _process_lock(session_key).release()


@asynccontextmanager
async def bulk_ingest_session(
    vault_path: Path,
    source_dir: Path | None = None,
    *,
    lock_mode: LockMode = "wait",
    lock_scope: LockScope = "source",
) -> AsyncIterator[None]:
    """Bulk-ingest coordination.

    Uses a per-session ``threading.Lock`` within each pod and ``fcntl.flock`` on a
    lock file under ``.cortex/`` so only one bulk ingest runs per ``source_dir``
    across replicas sharing the vault PVC.

    ``lock_scope='source'`` (default): one active job per ``source_dir``; different
    directories on the same vault may run in parallel.

    ``lock_scope='vault'``: exclusive across all bulk ingests for the vault.

    When the holding pod dies, the kernel releases ``flock`` automatically; the lock
    file may remain on disk but is not held.
    """
    vault_path = vault_path.resolve()
    if source_dir is not None:
        source_dir = normalize_source_dir(source_dir)

    session_key = _session_key(vault_path, source_dir, lock_scope)
    lock_path = bulk_ingest_lock_path(
        vault_path, source_dir if lock_scope == "source" else None
    )
    blocking = lock_mode == "wait"

    await asyncio.to_thread(
        _acquire_process_lock,
        session_key,
        vault_path,
        source_dir,
        lock_mode=lock_mode,
    )
    try:
        await asyncio.to_thread(
            _file_lock_enter,
            lock_path,
            vault_path,
            source_dir,
            blocking=blocking,
        )
        try:
            yield
        finally:
            await asyncio.to_thread(_file_lock_exit, lock_path)
    finally:
        await asyncio.to_thread(_release_process_lock, session_key)


@asynccontextmanager
async def vault_reindex_session(vault_path: Path) -> AsyncIterator[None]:
    """Serialize index rebuilds when multiple bulk ingests finish together."""
    session_key = f"{_vault_key(vault_path)}::reindex"
    async with _async_lock(session_key):
        yield
