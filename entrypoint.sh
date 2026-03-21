#!/bin/bash
# Auto-unload watchdog always starts — reads config from keepalive_options.json
# If no config file and no env var, it will wait for a config file to appear.
python3 /opt/auto_unload.py &

# lemonade-server mit Timestamp-Prefix auf stdout
exec lemonade-server serve 2>&1 | ts '[%Y-%m-%d %H:%M:%S]'