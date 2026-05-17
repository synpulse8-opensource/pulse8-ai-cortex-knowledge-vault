#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/stop.sh                 # Stop all services (QMD + Cortex)
#   ./scripts/stop.sh --cortex-only   # Stop only the Cortex container

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

CORTEX_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --cortex-only) CORTEX_ONLY=true ;;
        -h|--help)
            echo "Usage: $0 [--cortex-only]"
            echo ""
            echo "  --cortex-only   Stop only the Cortex container (leave QMD alone)."
            exit 0
            ;;
        *)
            echo "Unknown option: $arg (try --help)"
            exit 1
            ;;
    esac
done

if [ "$CORTEX_ONLY" = true ]; then
    echo "Stopping PULSE8.ai Cortex container..."
    docker compose -f docker-compose.yml -f docker-compose.cortex-only.yml stop cortex
    docker compose -f docker-compose.yml -f docker-compose.cortex-only.yml rm -f cortex
    echo "Cortex stopped. (QMD is not managed by Docker in cortex-only mode.)"
else
    echo "Stopping PULSE8.ai Cortex..."
    docker compose down
    echo "All services stopped."
fi
