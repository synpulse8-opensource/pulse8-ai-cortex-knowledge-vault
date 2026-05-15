#!/bin/sh
set -e

mkdir -p /home/qmd/.cache/qmd
chown -R qmd:qmd /home/qmd/.cache/qmd

exec gosu qmd "$@"
