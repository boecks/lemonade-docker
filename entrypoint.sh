#!/bin/bash
set -e
CACHE=/var/lib/lemonade/.cache/lemonade
BACKEND=/backends/rocm

if [ -f "$CACHE/config.json" ]; then
  python3 -c "
import json, pathlib
p = pathlib.Path('$CACHE/config.json')
c = json.loads(p.read_text())
c['no_fetch_executables'] = True
c['rocm_channel'] = 'nightly'
c.setdefault('llamacpp', {})
c['llamacpp']['rocm_bin'] = 'builtin'
p.write_text(json.dumps(c, indent=2))
print('config: fetch disabled, channel=nightly, rocm_bin=builtin')
"
fi

NIGHTLY="$CACHE/bin/llamacpp/rocm-nightly"

if [ -d "$NIGHTLY" ] && [ -f "$NIGHTLY/llama-server" ] && [ ! -L "$NIGHTLY/llama-server" ]; then
  mv "$NIGHTLY/llama-server" "$NIGHTLY/llama-server.orig"
  ln -sfn "$BACKEND/llama-server" "$NIGHTLY/llama-server"
  echo "swapped llama-server in $NIGHTLY"
elif [ -L "$NIGHTLY/llama-server" ]; then
  echo "llama-server already a symlink, skipping swap"
else
  echo "WARNING: $NIGHTLY/llama-server not found - did the bootstrap actually run?"
fi

# Make your build's libs win over the cache's libs.
# Your build's lib versions match what your llama-server was compiled against;
# the cache's libs are slightly older (note: libggml-base.so.0.10.0 in cache vs
# 0.11.0 in your build). Wrong libs would crash with symbol errors.
export LD_LIBRARY_PATH="$BACKEND${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host 0.0.0.0