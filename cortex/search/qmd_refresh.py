from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def periodic_qmd_refresh(qmd: Any, interval_seconds: float = 900) -> None:
    """Periodically call qmd.update() as a safety net for index freshness.

    Runs forever until cancelled.  Catches and logs errors from qmd.update()
    so a transient QMD failure never kills the background loop.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await qmd.update()
            logger.debug("Periodic QMD index refresh completed")
        except Exception:
            logger.warning("Periodic QMD index refresh failed", exc_info=True)
