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
