from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class DebouncedQMDUpdate:
    """Coalesces rapid qmd.update() calls into a single deferred invocation.

    Each call to ``schedule()`` resets the timer.  When the timer expires
    without another ``schedule()``, a single ``qmd.update()`` fires.
    """

    def __init__(self, qmd: Any, delay_seconds: float = 5.0) -> None:
        self._qmd = qmd
        self._delay = delay_seconds
        self._task: asyncio.Task | None = None

    def schedule(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            await asyncio.sleep(self._delay)
            await self._qmd.update()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning("Debounced QMD update failed", exc_info=True)
