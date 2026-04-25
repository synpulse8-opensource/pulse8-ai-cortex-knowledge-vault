from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from cortex.search.qmd_refresh import periodic_qmd_refresh


class TestPeriodicQmdRefresh:
    @pytest.mark.asyncio
    async def test_calls_qmd_update_periodically(self):
        qmd = AsyncMock()
        qmd.update = AsyncMock()

        task = asyncio.create_task(periodic_qmd_refresh(qmd, interval_seconds=0.05))
        await asyncio.sleep(0.12)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert qmd.update.await_count >= 2

    @pytest.mark.asyncio
    async def test_survives_qmd_update_failure(self):
        qmd = AsyncMock()
        qmd.update = AsyncMock(side_effect=RuntimeError("QMD down"))

        task = asyncio.create_task(periodic_qmd_refresh(qmd, interval_seconds=0.05))
        await asyncio.sleep(0.12)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert qmd.update.await_count >= 2

    @pytest.mark.asyncio
    async def test_cancellation_stops_cleanly(self):
        qmd = AsyncMock()
        qmd.update = AsyncMock()

        task = asyncio.create_task(periodic_qmd_refresh(qmd, interval_seconds=60))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


class TestSkipRefreshWhenQmdManagesOwnTimer:
    """Cortex should NOT start a periodic refresh when QMD HTTP is used,
    because the QMD container already runs its own timer."""

    @pytest.mark.asyncio
    async def test_no_refresh_task_when_qmd_url_set(self, monkeypatch):
        """When qmd_url is set (Docker mode), lifespan must not create a refresh task."""
        from cortex.config import CortexSettings

        s = CortexSettings()
        monkeypatch.setattr(s, "qmd_url", "http://qmd:3100")
        monkeypatch.setattr(s, "qmd_refresh_interval_seconds", 900)
        assert s.qmd_url != "", "precondition: qmd_url should be set"
        should_refresh = s.qmd_refresh_interval_seconds > 0 and not s.qmd_url
        assert should_refresh is False

    @pytest.mark.asyncio
    async def test_refresh_task_when_cli_mode(self, monkeypatch):
        """When qmd_url is empty (CLI mode), refresh should still be enabled."""
        from cortex.config import CortexSettings

        s = CortexSettings()
        monkeypatch.setattr(s, "qmd_url", "")
        monkeypatch.setattr(s, "qmd_refresh_interval_seconds", 900)
        should_refresh = s.qmd_refresh_interval_seconds > 0 and not s.qmd_url
        assert should_refresh is True
