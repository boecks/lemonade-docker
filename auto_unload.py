#!/usr/bin/env python3
"""
Lemonade idle model unloader.
Läuft als Hintergrundprozess im Container.
"""
import os, time, json, urllib.request, urllib.error
from datetime import datetime

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    print(f"[{ts()}] [auto-unload] {msg}", flush=True)

def parse_duration(s):
    """Parse duration string: 10m, 600s, 1h, 90 -> seconds. 0 or empty -> disabled."""
    if not s or s.strip() in ("0", ""):
        return 0
    s = s.strip()
    try:
        if s.endswith("h"):  return int(s[:-1]) * 3600
        if s.endswith("m"):  return int(s[:-1]) * 60
        if s.endswith("s"):  return int(s[:-1])
        return int(s)
    except ValueError:
        log(f"invalid LEMONADE_KEEPALIVE value: {s!r}, disabled.")
        return 0

IDLE_SECONDS   = parse_duration(os.environ.get("LEMONADE_KEEPALIVE", "0"))
URL            = "http://127.0.0.1:" + os.environ.get("LEMONADE_PORT", "8000")
CHECK_INTERVAL = 30

def api(path, data=None):
    try:
        body = json.dumps(data).encode() if data else None
        req  = urllib.request.Request(
            URL + path,
            data=body,
            headers={"Content-Type": "application/json"} if body else {}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None

def run():
    if IDLE_SECONDS <= 0:
        log("LEMONADE_KEEPALIVE not set or 0, disabled.")
        return

    log(f"idle timeout: {IDLE_SECONDS}s, check every {CHECK_INTERVAL}s")

    seen_at = {}  # model_name -> last activity timestamp

    while True:
        time.sleep(CHECK_INTERVAL)
        health = api("/api/v1/health")
        if not health:
            continue

        now    = time.time()
        loaded = {m["model_name"]: m for m in health.get("all_models_loaded", [])}

        # Nicht mehr geladene Modelle aufräumen
        for name in list(seen_at):
            if name not in loaded:
                del seen_at[name]

        for name, model in loaded.items():
            api_last_use = model.get("last_use", 0)

            if name not in seen_at:
                seen_at[name] = max(api_last_use, now)
                log(f"tracking '{name}'")
                continue

            if api_last_use > seen_at[name]:
                seen_at[name] = api_last_use

            # last_use vom Server hat Vorrang - aktualisiert sich bei jedem Request
            if api_last_use > seen_at[name]:
                seen_at[name] = api_last_use

            idle = now - seen_at[name]

            if idle >= IDLE_SECONDS:
                # Sicherheitscheck: last_use nochmal frisch holen kurz vor Unload
                fresh = api("/api/v1/health")
                if fresh:
                    fresh_loaded = {m["model_name"]: m for m in fresh.get("all_models_loaded", [])}
                    if name in fresh_loaded:
                        fresh_last_use = fresh_loaded[name].get("last_use", 0)
                        if fresh_last_use > seen_at[name]:
                            seen_at[name] = fresh_last_use
                            log(f"'{name}' activity detected just before unload, resetting timer")
                            continue
                log(f"unloading '{name}' (idle {idle:.0f}s)")
                api("/api/v1/unload", {"model_name": name})
                del seen_at[name]

if __name__ == "__main__":
    run()