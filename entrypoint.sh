#!/bin/bash

# Start the idle model watchdog in the background.
# It reads keepalive config from /root/.cache/lemonade/keepalive_options.json
# and will wait for a config file to appear if none exists yet.
python3 /opt/auto_unload.py &

# Start Lemonade Server with timestamps on stdout
exec lemonade-server serve 2>&1 | ts '[%Y-%m-%d %H:%M:%S]'