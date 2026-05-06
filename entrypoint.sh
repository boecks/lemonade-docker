#!/bin/bash
set -euo pipefail

# Background config applier: wait for lemond to come up, then apply all settings
(
  for i in {1..60}; do
    if /opt/lemonade/lemonade config >/dev/null 2>&1; then break; fi
    sleep 1
  done

  /opt/lemonade/lemonade config set \
    "llamacpp.backend=${LEMONADE_LLAMACPP_BACKEND:-rocm}" \
    "llamacpp.rocm_bin=${LEMONADE_LLAMACPP_ROCM_BIN:-builtin}" \
) &

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host "${LEMONADE_HOST:-0.0.0.0}"