#!/bin/bash
set -e

# Start the idle model watchdog in the background.
python3 /opt/auto_unload.py &

# Hand off to lemond. It reads config.json from the cache dir and creates
# one with upstream defaults if missing. Bind to 0.0.0.0 so the container
# is reachable from the host — everything else stays upstream default.
exec lemond --host 0.0.0.0