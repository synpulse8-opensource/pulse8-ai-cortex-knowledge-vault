#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "Stopping PULSE8.ai Cortex..."
docker compose down
echo "All services stopped."
