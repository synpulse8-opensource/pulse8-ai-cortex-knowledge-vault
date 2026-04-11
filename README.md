# Cortex

Agent-native knowledge OS built on Markdown files.

Cortex is a knowledge substrate where AI agents, AI assistants, and humans collaborate through a unified MCP interface backed by a graph engine.

## Quick Start

```bash
# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Start the persistent HTTP server (REST API + MCP at /mcp)
CORTEX_MCP_TRANSPORT=http CORTEX_VAULT_PATH=./example_vault uv run python scripts/serve.py

# Or run MCP server via stdio (for Claude Desktop stdio mode)
CORTEX_VAULT_PATH=./example_vault uv run python -m cortex.mcp
```

## Claude Desktop Configuration

### Option A: Persistent HTTP Server (recommended)

Start the server once, then configure Claude Desktop to connect via Streamable HTTP:

```bash
CORTEX_MCP_TRANSPORT=http CORTEX_VAULT_PATH=/path/to/your/vault uv run python scripts/serve.py
```

In your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cortex": {
      "url": "http://localhost:8420/mcp/"
    }
  }
}
```

### Option B: Stdio (Claude Desktop launches the server)

```json
{
  "mcpServers": {
    "cortex": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/cortex", "python", "-m", "cortex.mcp"],
      "env": {
        "CORTEX_VAULT_PATH": "/path/to/your/vault"
      }
    }
  }
}
```

## Architecture

- **Vault**: Filesystem-based persistence (Markdown + JSON)
- **Graph Engine**: NetworkX in-memory, JSON-persisted
- **Search**: QMD hybrid search (BM25 + vector + LLM re-ranking)
- **Compiler**: LLM-powered knowledge compilation (raw → wiki)
- **MCP Server**: stdio + Streamable HTTP transport for AI consumers
- **REST API**: FastAPI endpoints mirroring MCP tools
