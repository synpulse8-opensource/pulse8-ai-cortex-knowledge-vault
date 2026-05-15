#!/bin/sh
set -e

mkdir -p /home/qmd/.cache/qmd

exec "$@"
