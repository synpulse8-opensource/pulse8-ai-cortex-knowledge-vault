"""Start the Cortex server.

Supported transports (CORTEX_MCP_TRANSPORT):
  stdio  – MCP over stdin/stdout (default, for Claude Desktop stdio mode)
  http   – FastAPI + MCP streamable HTTP at /mcp (persistent server)
"""
from __future__ import annotations

import asyncio
import sys

from cortex.config import settings


def main() -> None:
    transport = settings.mcp_transport

    if transport == "stdio":
        from cortex.mcp.server import run_stdio

        asyncio.run(run_stdio())
    elif transport in ("http", "sse"):
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
