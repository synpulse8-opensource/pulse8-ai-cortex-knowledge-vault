#!/bin/sh
set -e

mkdir -p /home/qmd/.cache/qmd/models

# Initialize / repair index.yml so qmd collection commands work.
# Must be `collections: {}` (object) — `collections: []` (array) causes QMD to
# drop collection metadata on save, so `collection list` stays empty.
INDEX_YML=/home/qmd/.cache/qmd/index.yml
if [ ! -f "$INDEX_YML" ]; then
  printf '%s\n' 'collections: {}' > "$INDEX_YML"
elif grep -q '^collections: \[\]$' "$INDEX_YML" 2>/dev/null; then
  echo "Repairing QMD index.yml: collections: [] -> collections: {}"
  sed -i 's/^collections: \[\]$/collections: {}/' "$INDEX_YML"
fi

# Download models in background if not present
download_model() {
  name="$1"
  url="$2"
  dest="/home/qmd/.cache/qmd/models/$name"
  if [ ! -f "$dest" ] || [ ! -s "$dest" ]; then
    echo "Downloading model: $name"
    wget -q -O "$dest" "$url" || echo "Warning: failed to download $name"
  fi
}

(
  download_model "embeddinggemma-300M-Q8_0.gguf" \
    "https://huggingface.co/ggml-org/embeddinggemma-300M-GGUF/resolve/main/embeddinggemma-300M-Q8_0.gguf"
  download_model "qwen3-reranker-0.6b-q8_0.gguf" \
    "https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/resolve/main/qwen3-reranker-0.6b-q8_0.gguf"
  download_model "qmd-query-expansion-1.7B-q4_k_m.gguf" \
    "https://huggingface.co/tobil/qmd-query-expansion-1.7B-gguf/resolve/main/qmd-query-expansion-1.7B-q4_k_m.gguf"
  echo "Model downloads complete"
) &

exec "$@"
