#!/usr/bin/env python3
"""
Lemonade idle model unloader.
Läuft als Hintergrundprozess im Container.
"""
import os, time, json, urllib.request, urllib.error

def parse_duration(s):
    """Parse duration string: 10m, 600s, 1h, 90 -> seconds. 0 or empty -> disabled."""
    if not s or s.strip() in ("0", ""):
        return 0
    s = s.strip()
    try:
        if s.endswith("h"):  return int(s[:-1]) * 3600
        if s.endswith("m"):  return int(s[:-1]) * 60
        if s.endswith("s"):  return int(s[:-1])
        return int(s)  # plain number = seconds
    except ValueError:
        print(f"[auto-unload] invalid LEMONADE_KEEPALIVE value: {s!r}, disabled.", flush=True)
        return 0

IDLE_SECONDS = parse_duration(os.environ.get("LEMONADE_KEEPALIVE", "0"))
URL = "http://127.0.0.1:" + os.environ.get("LEMONADE_PORT", "8000")
CHECK_INTERVAL = 30

def api(path, data=None):
    try:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
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
        print("[auto-unload] LEMONADE_KEEPALIVE not set or 0, disabled.", flush=True)
        return

    print(f"[auto-unload] idle timeout: {IDLE_SECONDS}s, check every {CHECK_INTERVAL}s", flush=True)

    # last_use pro Modell tracken - wird beim ersten Sehen auf now() gesetzt
    # und nur durch einen echten API-Timestamp überschrieben wenn dieser neuer ist
    seen_at = {}  # model_name -> timestamp wann wir es zuerst gesehen haben

    while True:
        time.sleep(CHECK_INTERVAL)
        health = api("/api/v1/health")
        if not health:
            continue

        now = time.time()
        loaded = {m["model_name"]: m for m in health.get("all_models_loaded", [])}

        # Nicht mehr geladene Modelle aus seen_at entfernen
        for name in list(seen_at):
            if name not in loaded:
                del seen_at[name]

        for name, model in loaded.items():
            api_last_use = model.get("last_use", 0)

            if name not in seen_at:
                # Modell zum ersten Mal gesehen - jetzt als Referenz setzen
                seen_at[name] = now
                print(f"[auto-unload] tracking '{name}' (first seen)", flush=True)
                continue

            # Wenn last_use neuer ist als seen_at, echte Aktivität -> updaten
            if api_last_use > seen_at[name]:
                seen_at[name] = api_last_use

            idle = now - seen_at[name]
            if idle >= IDLE_SECONDS:
                print(f"[auto-unload] unloading '{name}' (idle {idle:.0f}s)", flush=True)
                api("/api/v1/unload", {"model_name": name})
                del seen_at[name]

if __name__ == "__main__":
    run()