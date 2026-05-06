#!/bin/bash
set -e

CACHE=/var/lib/lemonade/.cache/lemonade
BACKEND=/backends/rocm

# Force config to safe values BEFORE lemonade starts and reads it.
# Lemonade rewrites config.json on startup, but it reads it first to populate
# its in-memory state, and that state is what gets used for the run.
mkdir -p "$CACHE"
if [ -f "$CACHE/config.json" ]; then
  python3 -c "
import json, pathlib
p = pathlib.Path('$CACHE/config.json')
c = json.loads(p.read_text())
c.setdefault('llamacpp', {})
c['llamacpp']['rocm_bin'] = '$BACKEND'
c['llamacpp']['prefer_system'] = True
c['rocm_channel'] = 'stable'
c['no_fetch_executables'] = True
c['offline'] = True
p.write_text(json.dumps(c, indent=2))
print('config.json patched')
"
fi

# Bulletproof fallback: symlink ALL rocm channel cache dirs to your backend.
# Even if config gets reset to nightly, the binary at that path is yours.
mkdir -p "$CACHE/bin/llamacpp"
cd "$CACHE/bin/llamacpp"
for d in rocm rocm-stable rocm-nightly rocm-preview; do
  if [ ! -L "$d" ]; then
    rm -rf "$d"
    ln -sfn "$BACKEND" "$d"
    echo "linked $d -> $BACKEND"
  fi
done

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host 0.0.0.0