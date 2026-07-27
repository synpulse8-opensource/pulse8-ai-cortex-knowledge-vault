#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/stop.sh                 # Stop all services (QMD + Cortex, incl. native QMD if present)
#   ./scripts/stop.sh --native-qmd    # Stop the Cortex container and the native QMD process
#   ./scripts/stop.sh --cortex-only   # Stop only the Cortex container (leave QMD alone)

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/qmd_native.sh"

CORTEX_ONLY=false
NATIVE_QMD=false
for arg in "$@"; do
    case "$arg" in
        --cortex-only) CORTEX_ONLY=true ;;
        --native-qmd) NATIVE_QMD=true ;;
        -h|--help)
            echo "Usage: $0 [--native-qmd | --cortex-only]"
            echo ""
            echo "  --native-qmd    Stop the Cortex container and the native QMD process"
            echo "                  started by ./scripts/start.sh --native-qmd."
            echo "  --cortex-only   Stop only the Cortex container (leave QMD alone)."
            exit 0
            ;;
        *)
            echo "Unknown option: $arg (try --help)"
            exit 1
            ;;
    esac
done

if [ "$NATIVE_QMD" = true ]; then
    echo "Stopping PULSE8.ai Cortex container..."
    docker compose -f docker-compose.yml -f docker-compose.cortex-only.yml stop cortex
    docker compose -f docker-compose.yml -f docker-compose.cortex-only.yml rm -f cortex
    native_qmd_stop
    echo "All services stopped."
elif [ "$CORTEX_ONLY" = true ]; then
    echo "Stopping PULSE8.ai Cortex container..."
    docker compose -f docker-compose.yml -f docker-compose.cortex-only.yml stop cortex
    docker compose -f docker-compose.yml -f docker-compose.cortex-only.yml rm -f cortex
    echo "Cortex stopped. (QMD is not managed by Docker in cortex-only mode.)"
else
    echo "Stopping PULSE8.ai Cortex..."
    docker compose down
    # Clean up a native QMD too if one was started with --native-qmd
    # (quiet no-op when there is no pid file).
    native_qmd_stop
    echo "All services stopped."
fi
