#!/bin/bash
set -euo pipefail

/opt/lemonade/lemonade config set \
  "llamacpp.backend=${LEMONADE_LLAMACPP_BACKEND:-rocm}" \
  "llamacpp.rocm_bin=${LEMONADE_LLAMACPP_ROCM_BIN:-builtin}"

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host "${LEMONADE_HOST:-0.0.0.0}"