"""Tests for bulk ingest concurrency coordination."""
from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cortex.compiler.bulk_coordination import (
    BulkIngestBusyError,
    bulk_ingest_lock_path,
    bulk_ingest_session,
    normalize_source_dir,
)
from cortex.compiler.ingest_manifest import (
    load_manifest,
    manifest_path,
    record_compiled_file,
)


def _hold_flock_process(lock_path_str: str, started: mp.Event, release: mp.Event) -> None:
    import fcntl

    with open(lock_path_str, "w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        started.set()
        while not release.is_set():
            time.sleep(0.01)


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "raw").mkdir(parents=True)
    (vault / ".cortex").mkdir(parents=True)
    return vault


class TestBulkIngestSession:
    @pytest.mark.asyncio
    async def test_fail_mode_raises_for_same_source_dir(self, tmp_vault: Path) -> None:
        source = tmp_vault.parent / "inbox-a"
        source.mkdir()
        async with bulk_ingest_session(tmp_vault, source, lock_mode="wait"):
            with pytest.raises(BulkIngestBusyError):
                async with bulk_ingest_session(tmp_vault, source, lock_mode="fail"):
                    pass

    @pytest.mark.asyncio
    async def test_different_source_dirs_run_in_parallel(self, tmp_vault: Path) -> None:
        source_a = tmp_vault.parent / "inbox-a"
        source_b = tmp_vault.parent / "inbox-b"
        source_a.mkdir()
        source_b.mkdir()
        overlap: list[str] = []

        async def job(source: Path, name: str) -> None:
            async with bulk_ingest_session(tmp_vault, source, lock_mode="wait"):
                overlap.append(f"{name}-start")
                await asyncio.sleep(0.08)
                overlap.append(f"{name}-end")

        await asyncio.gather(job(source_a, "a"), job(source_b, "b"))
        assert "a-start" in overlap
        assert "b-start" in overlap
        assert overlap.index("a-start") < overlap.index("b-end") or overlap.index(
            "b-start"
        ) < overlap.index("a-end")

    @pytest.mark.asyncio
    async def test_vault_scope_serializes(self, tmp_vault: Path) -> None:
        order: list[str] = []

        async def job(name: str) -> None:
            async with bulk_ingest_session(
                tmp_vault, lock_mode="wait", lock_scope="vault"
            ):
                order.append(f"{name}-start")
                await asyncio.sleep(0.05)
                order.append(f"{name}-end")

        await asyncio.gather(job("a"), job("b"))
        assert order in (
            ["a-start", "a-end", "b-start", "b-end"],
            ["b-start", "b-end", "a-start", "a-end"],
        )

    @pytest.mark.asyncio
    async def test_creates_per_source_lock_file(self, tmp_vault: Path) -> None:
        source = tmp_vault.parent / "inbox-lock"
        source.mkdir()
        async with bulk_ingest_session(tmp_vault, source, lock_mode="wait"):
            assert bulk_ingest_lock_path(tmp_vault, source).exists()

    @pytest.mark.asyncio
    async def test_fail_mode_rejects_when_another_process_holds_flock(
        self, tmp_vault: Path
    ) -> None:
        """Simulates a second pod holding the vault lock file."""
        source = tmp_vault.parent / "inbox-cross-pod"
        source.mkdir()
        lock_path = bulk_ingest_lock_path(tmp_vault, source)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        started = mp.Event()
        release = mp.Event()
        proc = mp.Process(
            target=_hold_flock_process,
            args=(str(lock_path), started, release),
        )
        proc.start()
        try:
            assert started.wait(timeout=5)
            with pytest.raises(BulkIngestBusyError) as exc_info:
                async with bulk_ingest_session(tmp_vault, source, lock_mode="fail"):
                    pass
            assert exc_info.value.source_dir == source.resolve()
        finally:
            release.set()
            proc.join(timeout=5)
            if proc.is_alive():
                proc.kill()
                proc.join()

    @pytest.mark.asyncio
    async def test_fail_mode_rejects_parallel_same_pod(self, tmp_vault: Path) -> None:
        source = tmp_vault.parent / "inbox-parallel"
        source.mkdir()
        entered = asyncio.Event()

        async def hold_session() -> None:
            async with bulk_ingest_session(tmp_vault, source, lock_mode="wait"):
                entered.set()
                await asyncio.sleep(0.2)

        async def try_fail() -> None:
            await entered.wait()
            async with bulk_ingest_session(tmp_vault, source, lock_mode="fail"):
                pass

        task = asyncio.create_task(hold_session())
        try:
            await asyncio.wait_for(try_fail(), timeout=1.0)
            pytest.fail("expected BulkIngestBusyError")
        except BulkIngestBusyError:
            pass
        finally:
            await task

    def test_normalize_source_dir_trailing_slash(self, tmp_path: Path) -> None:
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        assert normalize_source_dir(inbox) == normalize_source_dir(Path(str(inbox) + "/"))

    def test_same_source_dir_uses_one_lock_file(self, tmp_vault: Path) -> None:
        source = tmp_vault.parent / "inbox"
        source.mkdir()
        alt = Path(str(source) + "/")
        assert bulk_ingest_lock_path(tmp_vault, source) == bulk_ingest_lock_path(
            tmp_vault, alt
        )

    @pytest.mark.asyncio
    async def test_lock_file_contains_metadata(self, tmp_vault: Path) -> None:
        source = tmp_vault.parent / "inbox-meta"
        source.mkdir()
        lock_path = bulk_ingest_lock_path(tmp_vault, source)
        async with bulk_ingest_session(tmp_vault, source, lock_mode="wait"):
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            assert data["source_dir"] == str(source.resolve())
            assert "pid" in data
            assert "host" in data
            assert "started_at" in data


class TestManifestConcurrency:
    def test_parallel_record_compiled_preserves_both_entries(self, tmp_vault: Path) -> None:
        raw_a = tmp_vault / "raw" / "a.txt"
        raw_b = tmp_vault / "raw" / "b.txt"
        raw_a.write_text("aaa")
        raw_b.write_text("bbb")

        def record(path: Path) -> None:
            record_compiled_file(tmp_vault, path)

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(record, [raw_a, raw_b]))

        manifest = json.loads(manifest_path(tmp_vault).read_text())
        assert "raw/a.txt" in manifest
        assert "raw/b.txt" in manifest

    def test_manifest_write_is_valid_json(self, tmp_vault: Path) -> None:
        raw = tmp_vault / "raw" / "one.txt"
        raw.write_text("content")
        record_compiled_file(tmp_vault, raw)
        data = json.loads(manifest_path(tmp_vault).read_text())
        assert load_manifest(tmp_vault) == data
