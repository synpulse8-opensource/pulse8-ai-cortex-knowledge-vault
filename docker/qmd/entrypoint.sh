#!/bin/sh
set -e

mkdir -p /home/qmd/.cache/qmd/models

# Copy QMD models to cache directory
for f in /opt/qmd/models/*.gguf; do
  name=$(basename "$f")
  if [ ! -f "/home/qmd/.cache/qmd/models/$name" ]; then
    cp "$f" "/home/qmd/.cache/qmd/models/$name"
    echo "Copied model: $name"
  fi
done

exec "$@"
