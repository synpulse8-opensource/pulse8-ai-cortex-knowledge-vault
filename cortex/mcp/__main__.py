from __future__ import annotations

import asyncio

from cortex.mcp.server import run_stdio

if __name__ == "__main__":
    asyncio.run(run_stdio())
