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
c.pop('rocm_channel', None)
p.write_text(json.dumps(c, indent=2))
print(f'patched: rocm_bin={c[\"llamacpp\"][\"rocm_bin\"]}')
"
fi

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host 0.0.0.0