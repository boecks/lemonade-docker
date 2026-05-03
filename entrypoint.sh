#!/bin/bash
set -e
python3 /opt/auto_unload.py &
exec /opt/bin/lemond --host 0.0.0.0