#!/bin/bash
set -e
CACHE=/var/lib/lemonade/.cache/lemonade
BACKEND=/backends/rocm
mkdir -p "$CACHE"

if [ -f "$CACHE/config.json" ]; then
  python3 -c "
import json, pathlib
p = pathlib.Path('$CACHE/config.json')
c = json.loads(p.read_text())
c.setdefault('llamacpp', {})
c['llamacpp']['rocm_bin'] = '$BACKEND'
c['no_fetch_executables'] = True
c.pop('rocm_channel', None)
p.write_text(json.dumps(c, indent=2))
print(f'patched: rocm_bin={c[\"llamacpp\"][\"rocm_bin\"]}, fetch disabled, channel removed')
"
fi

# Drop a marker file so Lemonade thinks the install is complete.
# Use a value that looks like a real upstream tag.
[ -f "$BACKEND/version.txt" ] || echo "b9999" > "$BACKEND/version.txt"

mkdir -p "$CACHE/bin/llamacpp"
cd "$CACHE/bin/llamacpp"
for d in rocm rocm-stable rocm-nightly rocm-preview; do
  if [ -L "$d" ] || [ -d "$d" ]; then
    rm -rf "$d"
  fi
  ln -sfn "$BACKEND" "$d"
  echo "linked $d -> $BACKEND"
done

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host 0.0.0.0