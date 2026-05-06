#!/bin/bash
set -e
CACHE=/var/lib/lemonade/.cache/lemonade
BACKEND=/backends/rocm

# Patch config (no_fetch=true, channel left alone since we have a real install)
if [ -f "$CACHE/config.json" ]; then
  python3 -c "
import json, pathlib
p = pathlib.Path('$CACHE/config.json')
c = json.loads(p.read_text())
c['no_fetch_executables'] = True
p.write_text(json.dumps(c, indent=2))
"
fi

# Replace just llama-server in whichever channels Lemonade has populated
for d in "$CACHE/bin/llamacpp"/rocm*; do
  [ -d "$d" ] || continue
  # Only replace if it's a real file, not already a symlink
  if [ -f "$d/llama-server" ] && [ ! -L "$d/llama-server" ]; then
    mv "$d/llama-server" "$d/llama-server.orig"
    ln -sfn "$BACKEND/llama-server" "$d/llama-server"
    echo "swapped llama-server in $d"
  fi
done

export LD_LIBRARY_PATH="$BACKEND${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host 0.0.0.0