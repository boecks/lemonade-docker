#!/bin/bash
set -e

CACHE=/var/lib/lemonade/.cache/lemonade
BACKEND=/backends/rocm
NIGHTLY="$CACHE/bin/llamacpp/rocm-nightly"

# Force nightly channel (only one with working gfx1201 binaries per issue #1787).
# Leave fetch enabled so Lemonade can do its install-then-validate dance unimpeded.
mkdir -p "$CACHE"
if [ -f "$CACHE/config.json" ]; then
  python3 -c "
import json, pathlib
p = pathlib.Path('$CACHE/config.json')
c = json.loads(p.read_text())
c['rocm_channel'] = 'nightly'
p.write_text(json.dumps(c, indent=2))
"
fi

# Background watcher: once Lemonade has installed the real binary,
# swap it for our build. Idempotent — runs only if it's still the original.
(
  while [ ! -f "$NIGHTLY/llama-server" ]; do sleep 2; done
  # Wait for install to finish writing
  sleep 5
  if [ -f "$NIGHTLY/llama-server" ] && [ ! -L "$NIGHTLY/llama-server" ]; then
    mv "$NIGHTLY/llama-server" "$NIGHTLY/llama-server.orig"
    ln -sfn "$BACKEND/llama-server" "$NIGHTLY/llama-server"
    echo "[entrypoint] swapped llama-server -> $BACKEND/llama-server"
  fi
) &

export LD_LIBRARY_PATH="$BACKEND${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host 0.0.0.0