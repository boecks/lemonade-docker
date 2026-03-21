#!/usr/bin/env python3
"""
Lemonade idle model unloader v2 — slot-aware with hot-reload config.

Reads keepalive durations from a JSON config file on every check cycle,
so you can change timeouts at runtime without restarting anything.

Config file priority (first found wins):
  1. $LEMONADE_KEEPALIVE_CONFIG  (explicit path)
  2. $LEMONADE_CACHE_DIR/keepalive_options.json
  3. ~/.cache/lemonade/keepalive_options.json

Config format (keepalive_options.json):
  {
    "_default": { "keep_alive": "10m" },
    "Qwen3.5-35B-A3B-GGUF": { "keep_alive": "30m" },
    "Llama-3.2-1B-Instruct-Hybrid": { "keep_alive": "5m" }
  }

OR directly inside recipe_options.json (if Lemonade ignores unknown keys):
  {
    "Qwen3.5-35B-A3B-GGUF": {
      "ctx_size": 147456,
      "llamacpp_args": "--reasoning off",
      "llamacpp_backend": "rocm",
      "keep_alive": "30m"
    }
  }

The watchdog also checks $LEMONADE_KEEPALIVE env var as a final fallback
for the default timeout. Set to 0 or omit to disable.

Durations: 10m, 600s, 1h, 600 (plain seconds). 0 = disabled for that model.
"""
import os, time, json, urllib.request, urllib.error, re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    print(f"[{ts()}] [auto-unload] {msg}", flush=True)

# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------
def parse_duration(s):
    if not s or str(s).strip() in ("0", ""):
        return 0
    s = str(s).strip()
    try:
        if s.endswith("h"):  return int(s[:-1]) * 3600
        if s.endswith("m"):  return int(s[:-1]) * 60
        if s.endswith("s"):  return int(s[:-1])
        return int(s)
    except ValueError:
        log(f"invalid duration value: {s!r}, returning 0")
        return 0

def format_duration(secs):
    if secs <= 0:
        return "disabled"
    if secs >= 3600 and secs % 3600 == 0:
        return f"{secs // 3600}h"
    if secs >= 60 and secs % 60 == 0:
        return f"{secs // 60}m"
    return f"{secs}s"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LEMONADE_PORT   = int(os.environ.get("LEMONADE_PORT", "8000"))
URL             = f"http://127.0.0.1:{LEMONADE_PORT}"
CHECK_INTERVAL  = int(os.environ.get("LEMONADE_CHECK_INTERVAL", "30"))
PRE_UNLOAD_WAIT = 3
ENV_DEFAULT     = parse_duration(os.environ.get("LEMONADE_KEEPALIVE", "0"))
EXCLUDE_PORTS   = set()

# ---------------------------------------------------------------------------
# Config file discovery
# ---------------------------------------------------------------------------
def find_config_paths():
    """Return list of config file paths to try, in priority order."""
    paths = []

    # 1. Explicit env var
    explicit = os.environ.get("LEMONADE_KEEPALIVE_CONFIG")
    if explicit:
        paths.append(explicit)

    # 2. recipe_options.json paths (read keep_alive from model entries)
    cache_dir = os.environ.get("LEMONADE_CACHE_DIR", os.path.expanduser("~/.cache/lemonade"))
    paths.append(os.path.join(cache_dir, "keepalive_options.json"))
    paths.append(os.path.join(cache_dir, "recipe_options.json"))

    return paths

CONFIG_PATHS = find_config_paths()

def load_keepalive_config():
    """
    Read keepalive config from JSON file. Re-reads on every call (hot-reload).
    Returns dict: { model_name: seconds, "_default": seconds }
    """
    result = {}

    for path in CONFIG_PATHS:
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError):
            continue

        if not isinstance(data, dict):
            continue

        for key, val in data.items():
            # Already have a value for this key from higher-priority file
            if key in result:
                continue

            if isinstance(val, dict):
                ka = val.get("keep_alive")
                if ka is not None:
                    result[key] = parse_duration(ka)
            elif isinstance(val, str):
                # Simple format: "model": "10m"
                result[key] = parse_duration(val)

    return result

# Cache config with short TTL to avoid reading file on every model check
# but still pick up changes quickly
_config_cache = {}
_config_cache_time = 0
CONFIG_CACHE_TTL = 10  # re-read file every 10 seconds

def get_idle_seconds(model_name):
    """Get keepalive duration for a model. Re-reads config file periodically."""
    global _config_cache, _config_cache_time
    now = time.time()
    if (now - _config_cache_time) >= CONFIG_CACHE_TTL:
        _config_cache = load_keepalive_config()
        _config_cache_time = now

    # Per-model from config file
    if model_name in _config_cache:
        return _config_cache[model_name]

    # _default from config file
    if "_default" in _config_cache:
        return _config_cache["_default"]

    # Env var fallback
    return ENV_DEFAULT

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def http_get_json(url, timeout=3):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

def api(path, data=None, timeout=5):
    try:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            URL + path,
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

# ---------------------------------------------------------------------------
# llama-server port discovery via /proc/net/tcp
# ---------------------------------------------------------------------------
def discover_llamaserver_port():
    try:
        with open("/proc/net/tcp", "r") as f:
            lines = f.readlines()[1:]
    except Exception:
        return None

    localhost_listeners = []
    for line in lines:
        parts = line.split()
        if len(parts) < 4 or parts[3] != "0A":
            continue
        addr_hex, port_hex = parts[1].split(":")
        port = int(port_hex, 16)
        if addr_hex == "0100007F":
            localhost_listeners.append(port)

    exclude = EXCLUDE_PORTS | {LEMONADE_PORT}
    candidates = [p for p in localhost_listeners if p not in exclude]

    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        candidates.sort(key=lambda p: abs(p - (LEMONADE_PORT + 1)))
        return candidates[0]
    return None

_cached_llama_port = None
_cached_llama_port_time = 0
LLAMA_CACHE_TTL = 60

def get_llamaserver_port():
    global _cached_llama_port, _cached_llama_port_time
    now = time.time()
    if _cached_llama_port and (now - _cached_llama_port_time) < LLAMA_CACHE_TTL:
        return _cached_llama_port
    port = discover_llamaserver_port()
    if port:
        if port != _cached_llama_port:
            log(f"llama-server discovered on port {port}")
        _cached_llama_port = port
        _cached_llama_port_time = now
    return _cached_llama_port

# ---------------------------------------------------------------------------
# Slot-based inference detection
# ---------------------------------------------------------------------------
def any_slot_processing():
    port = get_llamaserver_port()
    if not port:
        return None

    slots = http_get_json(f"http://127.0.0.1:{port}/slots")
    if slots and isinstance(slots, list):
        for slot in slots:
            if slot.get("is_processing", False):
                return True
        return False

    health = http_get_json(f"http://127.0.0.1:{port}/health")
    if health:
        return health.get("status") != "ok"

    return None

# ---------------------------------------------------------------------------
# Stats fingerprinting (secondary signal)
# ---------------------------------------------------------------------------
def get_stats():
    return api("/stats") or {}

def stats_fingerprint(s):
    if not s:
        return None
    return (
        s.get("input_tokens", 0),
        s.get("output_tokens", 0),
        s.get("tokens_per_second", 0),
        s.get("time_to_first_token", 0),
    )

# ---------------------------------------------------------------------------
# Build EXCLUDE_PORTS on startup
# ---------------------------------------------------------------------------
def init_exclude_ports():
    health = api("/api/v1/health")
    if health:
        ws_port = health.get("websocket_port")
        if ws_port:
            EXCLUDE_PORTS.add(int(ws_port))

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run():
    log("starting lemonade auto-unload watchdog")
    log(f"check interval: {CHECK_INTERVAL}s, pre-unload wait: {PRE_UNLOAD_WAIT}s")
    log(f"env fallback LEMONADE_KEEPALIVE: {format_duration(ENV_DEFAULT)}")
    log(f"config file search paths:")
    for p in CONFIG_PATHS:
        exists = os.path.isfile(p)
        log(f"  {p} ({'found' if exists else 'not found'})")

    # Show initial config
    cfg = load_keepalive_config()
    if cfg:
        log("loaded keepalive config:")
        for k, v in cfg.items():
            log(f"  {k}: {format_duration(v)}")
    elif ENV_DEFAULT <= 0:
        log("no config found yet, will poll until config file appears...")

    init_exclude_ports()

    # model_name -> {"last_activity": float, "last_stats": tuple|None, "idle_limit": int}
    tracked = {}

    while True:
        time.sleep(CHECK_INTERVAL)

        # If no config exists yet, wait quietly until one appears
        cfg_check = load_keepalive_config()
        if not cfg_check and ENV_DEFAULT <= 0:
            continue

        health = api("/api/v1/health")
        if not health:
            continue

        now    = time.time()
        stats  = get_stats()
        sfp    = stats_fingerprint(stats)
        loaded = {}
        for m in health.get("all_models_loaded", []):
            loaded[m["model_name"]] = m

        # Clean up models no longer loaded
        for name in list(tracked):
            if name not in loaded:
                del tracked[name]

        for name, model in loaded.items():
            idle_limit = get_idle_seconds(name)  # re-reads config if stale

            # Skip models with keepalive disabled
            if idle_limit <= 0:
                if name in tracked:
                    # Was tracked before, config changed to disable
                    log(f"'{name}' keepalive disabled, stopping tracking")
                    del tracked[name]
                continue

            api_last_use = model.get("last_use", 0)

            # --- First time seeing this model ---
            if name not in tracked:
                tracked[name] = {
                    "last_activity": now,
                    "prev_last_use": api_last_use,
                    "last_stats": sfp,
                    "idle_limit": idle_limit,
                }
                log(f"tracking '{name}' (keep_alive: {format_duration(idle_limit)})")
                continue

            info = tracked[name]

            # Log if keepalive changed (hot-reload feedback)
            if idle_limit != info.get("idle_limit"):
                log(f"'{name}' keep_alive changed: {format_duration(info['idle_limit'])} -> {format_duration(idle_limit)}")
                info["idle_limit"] = idle_limit

            # --- last_use changed => model was just used ---
            # last_use is a server uptime counter, NOT a unix timestamp.
            # We only care if the value changed since last check.
            if api_last_use != info["prev_last_use"]:
                info["last_activity"] = now
                info["prev_last_use"] = api_last_use

            # --- Stats changed => request just completed ---
            if sfp and info["last_stats"] and sfp != info["last_stats"]:
                info["last_activity"] = now

            info["last_stats"] = sfp

            # --- Check idle time ---
            idle = now - info["last_activity"]
            if idle < idle_limit:
                continue

            # ==========================================================
            # PRE-UNLOAD SAFETY CHECKS
            # ==========================================================
            log(f"'{name}' idle {idle:.0f}s >= {format_duration(idle_limit)}, verifying...")

            # Check 1: Any llama-server slot actively processing?
            busy = any_slot_processing()
            if busy is True:
                info["last_activity"] = now
                log(f"  '{name}' slot is_processing=true, aborting unload")
                continue
            elif busy is None:
                log(f"  '{name}' WARNING: could not query llama-server slots")

            # Check 2: Fresh Lemonade health
            fresh = api("/api/v1/health")
            if fresh:
                fl = {m["model_name"]: m for m in fresh.get("all_models_loaded", [])}
                if name in fl:
                    fresh_lu = fl[name].get("last_use", 0)
                    if fresh_lu != info["prev_last_use"]:
                        info["last_activity"] = time.time()
                        info["prev_last_use"] = fresh_lu
                        log(f"  '{name}' last_use changed, aborting unload")
                        continue

            # Check 3: Wait, recheck slots + stats
            time.sleep(PRE_UNLOAD_WAIT)

            busy2 = any_slot_processing()
            if busy2 is True:
                info["last_activity"] = time.time()
                log(f"  '{name}' slot became busy during wait, aborting unload")
                continue

            stats2 = get_stats()
            sfp2   = stats_fingerprint(stats2)
            if sfp2 and sfp and sfp2 != sfp:
                info["last_activity"] = time.time()
                info["last_stats"]    = sfp2
                log(f"  '{name}' stats changed during wait, aborting unload")
                continue

            # Re-read config one final time (maybe user just changed it)
            final_limit = get_idle_seconds(name)
            if final_limit <= 0:
                log(f"  '{name}' keepalive was just disabled in config, aborting unload")
                continue
            if final_limit > idle_limit:
                info["idle_limit"] = final_limit
                log(f"  '{name}' keepalive was just increased to {format_duration(final_limit)}, aborting unload")
                continue

            # All clear — unload
            log(f"unloading '{name}' (idle {idle:.0f}s >= {format_duration(idle_limit)})")
            result = api("/api/v1/unload", {"model_name": name})
            if result is not None:
                log(f"  '{name}' unloaded successfully")
            else:
                log(f"  '{name}' unload request failed")
            tracked.pop(name, None)

            # Invalidate port cache since llama-server will shut down
            global _cached_llama_port, _cached_llama_port_time
            _cached_llama_port = None
            _cached_llama_port_time = 0

if __name__ == "__main__":
    run()