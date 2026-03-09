#!/bin/bash
# Auto-unload im Hintergrund starten (nur wenn LEMONADE_KEEPALIVE > 0)
if [ "${LEMONADE_KEEPALIVE:-0}" -gt 0 ]; then
    python3 /opt/auto_unload.py &
fi

exec lemonade-server serve