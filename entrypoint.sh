#!/bin/bash
# Auto-unload im Hintergrund starten (nur wenn LEMONADE_KEEPALIVE gesetzt und != 0)
if [ -n "${LEMONADE_KEEPALIVE}" ] && [ "${LEMONADE_KEEPALIVE}" != "0" ]; then
    python3 /opt/auto_unload.py &
fi

# lemonade-server mit Timestamp-Prefix auf stdout
exec lemonade-server serve 2>&1 | ts '[%Y-%m-%d %H:%M:%S]'