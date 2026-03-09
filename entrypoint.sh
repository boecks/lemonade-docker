#!/bin/bash
# Auto-unload im Hintergrund starten (nur wenn LEMONADE_KEEPALIVE > 0)
if [ -n "${LEMONADE_KEEPALIVE}" ] && [ "${LEMONADE_KEEPALIVE}" != "0" ]; then
    python3 /opt/auto_unload.py &
fi

exec lemonade-server serve