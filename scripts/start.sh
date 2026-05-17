#!/usr/bin/env bash
set -euo pipefail

# PULSE8.ai Cortex — one-click launcher
# Validates environment, then starts QMD + PULSE8.ai Cortex via Docker Compose.
#
# Usage:
#   ./scripts/start.sh                 # Start all services (QMD + Cortex)
#   ./scripts/start.sh --cortex-only   # Start only Cortex container (run QMD natively)

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/env_check.sh"

# ── Parse flags ─────────────────────────────────────────────────────
CORTEX_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --cortex-only) CORTEX_ONLY=true ;;
        -h|--help)
            echo "Usage: $0 [--cortex-only]"
            echo ""
            echo "  --cortex-only   Start only the Cortex container."
            echo "                  QMD must be running separately (e.g. natively)."
            echo "                  Set QMD_URL in .env to point to your QMD instance."
            echo "                  Default: http://host.docker.internal:3100"
            echo ""
            echo "  To run QMD natively (with GPU acceleration on macOS):"
            echo "    npm install -g @tobilu/qmd"
            echo "    VAULT_PATH=./example_vault node docker/qmd/server.mjs"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg (try --help)"
            exit 1
            ;;
    esac
done

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
if [ "$CORTEX_ONLY" = true ]; then
    QMD_URL="${QMD_URL:-http://host.docker.internal:3100}"
    export CORTEX_QMD_URL="$QMD_URL"

    echo "Starting PULSE8.ai Cortex (cortex-only mode)..."
    echo "  Vault:       $VAULT_DIR"
    echo "  Model:       $COMPILER_MODEL"
    echo "  LLM URL:     $LLM_BASE_URL"
    echo "  QMD URL:     $QMD_URL  (external)"
    echo "  QMD Refresh: ${QMD_REFRESH_INTERVAL_SECONDS}s"
    echo ""

    COMPOSE_FILES="-f docker-compose.yml -f docker-compose.cortex-only.yml"
    docker compose $COMPOSE_FILES build cortex
    docker compose $COMPOSE_FILES up -d --no-deps cortex

    echo ""
    echo "Waiting for Cortex to start..."
    for i in $(seq 1 15); do
        if docker compose $COMPOSE_FILES ps cortex --format '{{.Status}}' 2>/dev/null | grep -q "Up"; then
            echo "Cortex container is up."
            break
        fi
        sleep 2
    done

    echo ""
    echo "✔ PULSE8.ai Cortex is running (cortex-only mode)!"
    echo ""
    echo "  MCP endpoint:  http://localhost:8420/mcp/"
    echo "  REST API:      http://localhost:8420/api/v1/"
    echo "  QMD search:    $QMD_URL  (external — make sure QMD is running)"
    echo ""
    echo "  View logs:     docker compose logs -f cortex"
    echo "  Stop:          ./scripts/stop.sh --cortex-only"
    echo ""
else
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
fi
