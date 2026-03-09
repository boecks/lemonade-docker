#!/usr/bin/env python3
"""
Lemonade idle model unloader.
Läuft als Hintergrundprozess im Container.
"""
import os, time, json, urllib.request, urllib.error

IDLE_SECONDS = int(os.environ.get("LEMONADE_KEEPALIVE", 0)) * 60
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

    while True:
        time.sleep(CHECK_INTERVAL)
        health = api("/api/v1/health")
        if not health:
            continue

        now = time.time()
        for model in health.get("all_models_loaded", []):
            name = model["model_name"]
            idle = now - model.get("last_use", now)
            if idle >= IDLE_SECONDS:
                print(f"[auto-unload] unloading '{name}' (idle {idle:.0f}s)", flush=True)
                api("/api/v1/unload", {"model_name": name})

if __name__ == "__main__":
    run()