"""Start the Cortex MCP server (stdio or SSE)."""
from __future__ import annotations

import asyncio
import sys

from cortex.config import settings


def main() -> None:
    transport = settings.mcp_transport

    if transport == "stdio":
        from cortex.mcp.server import run_stdio

        asyncio.run(run_stdio())
    elif transport == "sse":
        import uvicorn

        uvicorn.run(
            "cortex.main:app",
            host=settings.mcp_sse_host,
            port=settings.mcp_sse_port,
        )
    else:
        print(f"Unknown transport: {transport}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
