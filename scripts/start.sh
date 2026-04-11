#!/usr/bin/env bash
set -euo pipefail

# Start QMD container + Cortex locally
# Usage: ./scripts/start.sh
#
# Required env vars:
#   CORTEX_LLM_API_KEY    - OpenRouter (or compatible) API key
#
# Optional env vars:
#   CORTEX_COMPILER_MODEL - LLM model (default: anthropic/claude-sonnet-4-20250514)
#   CORTEX_VAULT_PATH     - Path to vault (default: ./example_vault)

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

export CORTEX_VAULT_PATH="${CORTEX_VAULT_PATH:-./example_vault}"
export CORTEX_MCP_TRANSPORT=http
export CORTEX_QMD_URL=http://localhost:3100

echo "Starting QMD container..."
docker compose up qmd -d --build --wait

echo "QMD ready at http://localhost:3100"
echo "Starting Cortex server..."
echo "  Vault:    $CORTEX_VAULT_PATH"
echo "  Model:    ${CORTEX_COMPILER_MODEL:-anthropic/claude-sonnet-4-20250514}"
echo "  MCP:      http://localhost:8420/mcp/"
echo "  REST API: http://localhost:8420/api/v1/"
echo ""

uv run python scripts/serve.py
