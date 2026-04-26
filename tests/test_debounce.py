"""Tests for debounced QMD update."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest


class TestDebouncedQMDUpdate:
    @pytest.mark.asyncio
    async def test_single_call_triggers_update(self):
        """A single debounced request should eventually fire update()."""
        from cortex.search.qmd_debounce import DebouncedQMDUpdate

        qmd = AsyncMock()
        qmd.update = AsyncMock()
        debouncer = DebouncedQMDUpdate(qmd, delay_seconds=0.05)

        debouncer.schedule()
        await asyncio.sleep(0.1)

        assert qmd.update.await_count == 1

    @pytest.mark.asyncio
    async def test_rapid_calls_coalesce_into_one(self):
        """Multiple rapid schedule() calls within the window should fire only once."""
        from cortex.search.qmd_debounce import DebouncedQMDUpdate

        qmd = AsyncMock()
        qmd.update = AsyncMock()
        debouncer = DebouncedQMDUpdate(qmd, delay_seconds=0.1)

        for _ in range(5):
            debouncer.schedule()
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.15)
        assert qmd.update.await_count == 1

    @pytest.mark.asyncio
    async def test_spaced_calls_trigger_multiple_updates(self):
        """Calls spaced beyond the delay window should each trigger an update."""
        from cortex.search.qmd_debounce import DebouncedQMDUpdate

        qmd = AsyncMock()
        qmd.update = AsyncMock()
        debouncer = DebouncedQMDUpdate(qmd, delay_seconds=0.05)

        debouncer.schedule()
        await asyncio.sleep(0.1)

        debouncer.schedule()
        await asyncio.sleep(0.1)

        assert qmd.update.await_count == 2

    @pytest.mark.asyncio
    async def test_survives_update_failure(self):
        """A failing update() should not break subsequent debounced calls."""
        from cortex.search.qmd_debounce import DebouncedQMDUpdate

        qmd = AsyncMock()
        call_count = 0

        async def _failing_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("QMD down")

        qmd.update = AsyncMock(side_effect=_failing_then_ok)
        debouncer = DebouncedQMDUpdate(qmd, delay_seconds=0.05)

        debouncer.schedule()
        await asyncio.sleep(0.1)

        debouncer.schedule()
        await asyncio.sleep(0.1)

        assert qmd.update.await_count == 2
