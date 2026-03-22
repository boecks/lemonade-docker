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
for the default timeout.

Durations: 10m, 600s, 1h, 600 (plain seconds).
Special values:
  0   = immediate unload (unload on next check cycle after model loads)
  -1  = never unload (model stays loaded indefinitely)
  omit / no config = watchdog ignores the model (not tracked)
"""
import os, time, json, hashlib, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Sentinel for "never unload"
# ---------------------------------------------------------------------------
NEVER = -1

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def script_hash():
    """Short hash of this script file for identifying deployed version."""
    try:
        data = Path(__file__).read_bytes()
        return hashlib.sha256(data).hexdigest()[:8]
    except Exception:
        return "unknown"

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    print(f"[{ts()}] [auto-unload] {msg}", flush=True)

# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------
def parse_duration(s):
    """Parse a duration string into seconds.

    Returns:
        int: seconds (>0), 0 for immediate unload, or NEVER (-1) for never unload.
        None: if the value is empty/missing/unparseable — means "no opinion",
              so the fallback chain continues (_default -> env var).
    """
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    if s == "-1":
        return NEVER
    try:
        if s.endswith("h"):  return int(s[:-1]) * 3600
        if s.endswith("m"):  return int(s[:-1]) * 60
        if s.endswith("s"):  return int(s[:-1])
        return int(s)
    except ValueError:
        log(f"invalid duration value: {s!r}, ignoring")
        return None

def format_duration(secs):
    if secs == NEVER:
        return "never"
    if secs <= 0:
        return "immediate"
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
ENV_DEFAULT     = parse_duration(os.environ.get("LEMONADE_KEEPALIVE"))
EXCLUDE_PORTS   = set()

# ---------------------------------------------------------------------------
# Config file discovery
# ---------------------------------------------------------------------------
def find_config_paths():
    """Return list of config file paths to try, in priority order."""
    paths = []
    explicit = os.environ.get("LEMONADE_KEEPALIVE_CONFIG")
    if explicit:
        paths.append(explicit)
    cache_dir = os.environ.get("LEMONADE_CACHE_DIR", os.path.expanduser("~/.cache/lemonade"))
    paths.append(os.path.join(cache_dir, "keepalive_options.json"))
    paths.append(os.path.join(cache_dir, "recipe_options.json"))
    return paths

CONFIG_PATHS = find_config_paths()

def load_keepalive_config():
    """
    Read keepalive config from JSON file. Re-reads on every call (hot-reload).
    Returns dict: { model_name: seconds_or_NEVER, "_default": seconds_or_NEVER }
    Only includes keys where a valid keep_alive value was found.
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
            if key in result:
                continue
            if isinstance(val, dict):
                ka = val.get("keep_alive")
                if ka is not None:
                    parsed = parse_duration(ka)
                    if parsed is not None:
                        result[key] = parsed
            elif isinstance(val, str):
                parsed = parse_duration(val)
                if parsed is not None:
                    result[key] = parsed
    return result

# Cache config with short TTL
_config_cache = {}
_config_cache_time = 0
CONFIG_CACHE_TTL = 10

def get_idle_seconds(model_name):
    """Get keepalive duration for a model. Re-reads config file periodically.

    Fallback chain: per-model config -> _default config -> env var -> None.

    Returns:
        int: seconds (>0), 0 for immediate, NEVER (-1) for never unload.
        None: no config covers this model — don't track it.
    """
    global _config_cache, _config_cache_time
    now = time.time()
    if (now - _config_cache_time) >= CONFIG_CACHE_TTL:
        _config_cache = load_keepalive_config()
        _config_cache_time = now
    if model_name in _config_cache:
        return _config_cache[model_name]
    if "_default" in _config_cache:
        return _config_cache["_default"]
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
    log(f"starting (version: {script_hash()})")
    log(f"check interval: {CHECK_INTERVAL}s, pre-unload wait: {PRE_UNLOAD_WAIT}s")
    log(f"env fallback LEMONADE_KEEPALIVE: {format_duration(ENV_DEFAULT) if ENV_DEFAULT is not None else 'not set'}")
    log(f"config file search paths:")
    for p in CONFIG_PATHS:
        exists = os.path.isfile(p)
        log(f"  {p} ({'found' if exists else 'not found'})")

    cfg = load_keepalive_config()
    if cfg:
        log("loaded keepalive config:")
        for k, v in cfg.items():
            log(f"  {k}: {format_duration(v)}")
    elif ENV_DEFAULT is None:
        log("no config found yet, will poll until config file appears...")

    init_exclude_ports()

    tracked = {}

    while True:
        time.sleep(CHECK_INTERVAL)

        cfg_check = load_keepalive_config()
        if not cfg_check and ENV_DEFAULT is None:
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
            idle_limit = get_idle_seconds(name)

            # None = not configured, don't track
            if idle_limit is None:
                if name in tracked:
                    log(f"'{name}' keepalive removed from config, stopping tracking")
                    del tracked[name]
                continue

            # NEVER = keep loaded indefinitely
            if idle_limit == NEVER:
                if name not in tracked:
                    log(f"tracking '{name}' (keep_alive: never)")
                    tracked[name] = {"idle_limit": NEVER}
                elif tracked[name].get("idle_limit") != NEVER:
                    log(f"'{name}' keep_alive changed: {format_duration(tracked[name]['idle_limit'])} -> never")
                    tracked[name] = {"idle_limit": NEVER}
                continue

            api_last_use = model.get("last_use", 0)

            # --- First time seeing this model ---
            if name not in tracked:
                tracked[name] = {
                    "last_activity": now,
                    "prev_last_use": api_last_use,
                    "last_stats": sfp,
                    "idle_limit": idle_limit,
                    "logged_idle_start": False,
                }
                if idle_limit == 0:
                    log(f"tracking '{name}' (keep_alive: immediate — will unload on next cycle)")
                else:
                    log(f"tracking '{name}' (keep_alive: {format_duration(idle_limit)})")
                continue

            info = tracked[name]

            # Log if keepalive changed (hot-reload feedback)
            if idle_limit != info.get("idle_limit"):
                log(f"'{name}' keep_alive changed: {format_duration(info['idle_limit'])} -> {format_duration(idle_limit)}")
                info["idle_limit"] = idle_limit

            # --- Immediate unload: skip activity tracking, go straight to unload ---
            if idle_limit == 0:
                log(f"'{name}' keep_alive is immediate, verifying before unload...")
                busy = any_slot_processing()
                if busy is True:
                    log(f"  '{name}' slot is_processing=true, deferring immediate unload")
                    continue
                elif busy is None:
                    log(f"  '{name}' WARNING: could not query llama-server slots")

                time.sleep(PRE_UNLOAD_WAIT)

                busy2 = any_slot_processing()
                if busy2 is True:
                    log(f"  '{name}' slot became busy during wait, deferring immediate unload")
                    continue

                final_limit = get_idle_seconds(name)
                if final_limit is None:
                    log(f"  '{name}' keepalive was just removed from config, aborting unload")
                    del tracked[name]
                    continue
                if final_limit == NEVER:
                    log(f"  '{name}' keepalive was just set to never, aborting unload")
                    info["idle_limit"] = NEVER
                    continue
                if final_limit > 0:
                    log(f"  '{name}' keepalive was just changed to {format_duration(final_limit)}, aborting immediate unload")
                    info["idle_limit"] = final_limit
                    info["last_activity"] = now
                    info["logged_idle_start"] = False
                    continue

                log(f"unloading '{name}' (immediate)")
                result = api("/api/v1/unload", {"model_name": name})
                if result is not None:
                    log(f"  '{name}' unloaded successfully")
                else:
                    log(f"  '{name}' unload request failed")
                tracked.pop(name, None)

                global _cached_llama_port, _cached_llama_port_time
                _cached_llama_port = None
                _cached_llama_port_time = 0
                continue

            # --- Normal timed keepalive ---
            was_active = False
            if api_last_use != info["prev_last_use"]:
                info["prev_last_use"] = api_last_use
                was_active = True

            if sfp and info["last_stats"] and sfp != info["last_stats"]:
                was_active = True

            info["last_stats"] = sfp

            if was_active:
                was_idle = (now - info["last_activity"]) >= CHECK_INTERVAL * 2
                info["last_activity"] = now
                info["logged_idle_start"] = False
                if was_idle:
                    log(f"'{name}' activity detected, idle timer reset")

            # --- Check idle time ---
            idle = now - info["last_activity"]
            if idle < idle_limit:
                # Log once when idle period starts
                if not info.get("logged_idle_start") and idle >= CHECK_INTERVAL:
                    info["logged_idle_start"] = True
                    log(f"'{name}' idle, unload in {format_duration(max(0, int(idle_limit - idle)))}")

                # Progress logging for longer keepalives
                if idle_limit > CHECK_INTERVAL * 3:
                    report_interval = max(idle_limit // 3, 30)
                    prev_idle = idle - CHECK_INTERVAL
                    if prev_idle < 0:
                        prev_idle = 0
                    if int(idle / report_interval) > int(prev_idle / report_interval):
                        log(f"'{name}' idle {format_duration(int(idle))} / {format_duration(idle_limit)}")

                continue

            # ==========================================================
            # PRE-UNLOAD SAFETY CHECKS
            # ==========================================================
            log(f"'{name}' idle {format_duration(int(idle))}, unloading... (keep_alive: {format_duration(idle_limit)})")

            # Check 1: Any llama-server slot actively processing?
            busy = any_slot_processing()
            if busy is True:
                info["last_activity"] = now
                info["logged_idle_start"] = False
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
                        info["logged_idle_start"] = False
                        log(f"  '{name}' last_use changed, aborting unload")
                        continue

            # Check 3: Wait, recheck slots + stats
            time.sleep(PRE_UNLOAD_WAIT)

            busy2 = any_slot_processing()
            if busy2 is True:
                info["last_activity"] = time.time()
                info["logged_idle_start"] = False
                log(f"  '{name}' slot became busy during wait, aborting unload")
                continue

            stats2 = get_stats()
            sfp2   = stats_fingerprint(stats2)
            if sfp2 and sfp and sfp2 != sfp:
                info["last_activity"] = time.time()
                info["last_stats"]    = sfp2
                info["logged_idle_start"] = False
                log(f"  '{name}' stats changed during wait, aborting unload")
                continue

            # Re-read config one final time
            final_limit = get_idle_seconds(name)
            if final_limit is None:
                log(f"  '{name}' keepalive was just removed from config, aborting unload")
                continue
            if final_limit == NEVER:
                log(f"  '{name}' keepalive was just set to never, aborting unload")
                continue
            if final_limit > idle_limit:
                info["idle_limit"] = final_limit
                log(f"  '{name}' keepalive was just increased to {format_duration(final_limit)}, aborting unload")
                continue

            # All clear — unload
            log(f"  '{name}' all clear, sending unload request")
            result = api("/api/v1/unload", {"model_name": name})
            if result is not None:
                log(f"  '{name}' unloaded successfully")
            else:
                log(f"  '{name}' unload request failed")
            tracked.pop(name, None)

            _cached_llama_port = None
            _cached_llama_port_time = 0

if __name__ == "__main__":
    run()