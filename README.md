# Cortex

Agent-native knowledge OS built on Markdown files.

Cortex is a knowledge substrate where AI agents, AI assistants, and humans collaborate through a unified MCP interface backed by a graph engine.

## Quick Start

```bash
# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Start the server
uv run uvicorn cortex.main:app --host 0.0.0.0 --port 8420

# Or run MCP server (stdio)
uv run python -m cortex.mcp.server
```

## Architecture

- **Vault**: Filesystem-based persistence (Markdown + JSON)
- **Graph Engine**: NetworkX in-memory, JSON-persisted
- **Search**: QMD hybrid search (BM25 + vector + LLM re-ranking)
- **Compiler**: LLM-powered knowledge compilation (raw → wiki)
- **MCP Server**: stdio + SSE transport for AI consumers
- **REST API**: FastAPI endpoints mirroring MCP tools
