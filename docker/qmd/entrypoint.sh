#!/bin/sh
set -e

chown -R qmd:qmd /home/qmd/.cache/qmd

exec su-exec qmd "$@"
