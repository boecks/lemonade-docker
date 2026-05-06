#!/bin/bash
set -euo pipefail

# Pre-server config (works without lemond running)
/opt/lemonade/lemonade config set \
  "llamacpp.backend=${LEMONADE_LLAMACPP_BACKEND:-rocm}" \
  "ctx_size=${LEMONADE_CTX_SIZE:-4096}" \
  "max_loaded_models=${LEMONADE_MAX_LOADED_MODELS:-1}" \
  "log_level=${LEMONADE_LOG_LEVEL:-info}"

# Background hot-swap: wait for lemond, then apply *_bin keys.
# Runs as a child of the entrypoint; lemond is PID 1 via exec below.
(
  for i in {1..60}; do
    if /opt/lemonade/lemonade config >/dev/null 2>&1; then break; fi
    sleep 1
  done
  /opt/lemonade/lemonade config set \
    "llamacpp.rocm_bin=${LEMONADE_LLAMACPP_ROCM_BIN:-builtin}"
) &

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host "${LEMONADE_HOST:-0.0.0.0}"