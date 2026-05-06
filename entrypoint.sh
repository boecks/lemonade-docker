#!/bin/bash
set -e
CACHE=/var/lib/lemonade/.cache/lemonade

# Reset config to defaults that allow fetch
if [ -f "$CACHE/config.json" ]; then
  python3 -c "
import json, pathlib
p = pathlib.Path('$CACHE/config.json')
c = json.loads(p.read_text())
c['no_fetch_executables'] = False
c['offline'] = False
c.pop('rocm_channel', None)
# Force nightly since per your issue, that's the only working channel for gfx1201
c['rocm_channel'] = 'nightly'
c.setdefault('llamacpp', {})
c['llamacpp']['rocm_bin'] = 'builtin'   # let lemonade manage
p.write_text(json.dumps(c, indent=2))
print('config reset for bootstrap fetch')
"
fi

python3 /opt/auto_unload.py &
exec /opt/lemonade/lemond --host 0.0.0.0