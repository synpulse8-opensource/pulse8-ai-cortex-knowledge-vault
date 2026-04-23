#!/usr/bin/env bash
set -euo pipefail

# PULSE8.ai Cortex — one-click launcher
# Validates environment, then starts QMD + PULSE8.ai Cortex via Docker Compose.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/env_check.sh"

# ── Load existing .env if present ────────────────────────────────────
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# ── Validate / prompt for missing config ─────────────────────────────
if ! check_required_env 2>/dev/null; then
    prompt_missing_env
fi

apply_defaults

# ── Verify Docker is running ─────────────────────────────────────────
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

# ── Persist config to .env for Docker Compose ────────────────────────
write_env_file .env
echo "Configuration saved to .env"

# ── Launch ───────────────────────────────────────────────────────────
echo ""
echo "Starting PULSE8.ai Cortex..."
echo "  Vault:       $VAULT_DIR"
echo "  Model:       $COMPILER_MODEL"
echo "  LLM URL:     $LLM_BASE_URL"
echo "  QMD Refresh: ${QMD_REFRESH_INTERVAL_SECONDS}s"
echo ""

docker compose up --build -d

echo ""
echo "Waiting for services to become healthy..."
docker compose up --wait

echo ""
echo "✔ PULSE8.ai Cortex is running!"
echo ""
echo "  MCP endpoint:  http://localhost:8420/mcp/"
echo "  REST API:      http://localhost:8420/api/v1/"
echo "  QMD search:    http://localhost:3100/"
echo ""
echo "  View logs:     docker compose logs -f"
echo "  Stop:          docker compose down"
echo ""
