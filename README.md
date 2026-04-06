# lemonade-docker

Dockerized [Lemonade Server](https://github.com/lemonade-sdk/lemonade) with an idle model watchdog that adds **per-model keepalive** — a feature Lemonade doesn't have natively yet.

## The Problem

Lemonade Server has no built-in way to automatically unload idle models from GPU memory. If you're running coding agents like OpenCode or Claude Code that have long inference times (minutes of token generation), a naive timeout-based approach will kill models mid-inference. Ollama solves this with a per-request `keep_alive` parameter — Lemonade has nothing equivalent.

## The Solution

A lightweight Python watchdog (`auto_unload.py`) that runs alongside Lemonade Server inside the container. It:

- **Detects active inference** by querying the underlying llama-server's `/slots` endpoint (`is_processing` flag) — will never unload a model mid-generation
- **Supports per-model keepalive durations** via a hot-reloadable JSON config file — no container restart needed
- **Auto-discovers the llama-server port** via `/proc/net/tcp` — no hardcoded ports
- **Triple safety check** before every unload: slot status, fresh health check, and a brief wait with recheck

## Quick Start

```bash
git clone https://github.com/YOUR_USER/lemonade-docker.git
cd lemonade-docker

# Copy and edit the example files
cp keepalive_options.json.example lemonade-data/keepalive_options.json
cp docker-compose.yml.example docker-compose.yml

# Edit docker-compose.yml to match your paths and GPU setup
# Edit lemonade-data/keepalive_options.json for your models

# Build and run
docker compose up -d
```

## Configuration

### Keepalive Config (`keepalive_options.json`)

Mount this file to `/root/.cache/lemonade` inside the container. The watchdog re-reads it every 10 seconds, so changes take effect at runtime without restarting anything.

```json
{
  "_default": { "keep_alive": "10m" },
  "Qwen3.5-35B-A3B-GGUF": { "keep_alive": "30m" },
  "Qwen3.5-4B-GGUF": { "keep_alive": "5m" }
}
```

- `_default` applies to any model without a specific entry
- Duration formats: `30m`, `1h`, `600s`, or `600` (plain seconds)
- Special values:
  - `"0"` → immediate unload (unload on next check cycle)
  - `"-1"` → never unload (model stays loaded indefinitely)
  - omit or empty → watchdog ignores the model (not tracked)
- Changes are picked up within one check cycle (~30 seconds)

### Model Config (`recipe_options.json`)

Lemonade's own per-model configuration. You can also place keepalive settings directly here:

```json
{
  "Qwen3.5-35B-A3B-GGUF": {
    "ctx_size": 147456,
    "llamacpp_args": "--reasoning off",
    "llamacpp_backend": "rocm",
    "keep_alive": "30m"
  }
}
```

Keepalive settings in `recipe_options.json` take precedence over `keepalive_options.json` when both files exist.

### Environment Variables

The watchdog supports these optional env vars as fallbacks:

| Variable | Default | Description |
|---|---|---|
| `LEMONADE_KEEPALIVE` | *(not set)* | Fallback default keepalive if no config file exists |
| `LEMONADE_CHECK_INTERVAL` | `30` | Seconds between watchdog checks |
| `LEMONADE_KEEPALIVE_CONFIG` | *(auto-discovered)* | Explicit path to keepalive config file |
| `LEMONADE_CACHE_DIR` | `~/.cache/lemonade` | Default directory for config files |
| `LEMONADE_PORT` | `8000` | Port of the Lemonade server |

The config file always takes priority over environment variables.

## How It Works

### Idle Detection

Every 30 seconds the watchdog:

1. Queries Lemonade's `/api/v1/health` for loaded models and their `last_use` timestamps
2. Compares `/stats` fingerprints to detect recently completed requests
3. If a model exceeds its keepalive duration, begins pre-unload verification

### Pre-Unload Safety Checks

Before unloading, the watchdog runs three checks to ensure no inference is in progress:

1. **Slot check** — queries the llama-server's `/slots` endpoint for `is_processing: true` on any slot
2. **Fresh health check** — re-reads `last_use` from Lemonade to catch requests that just started
3. **Wait and recheck** — waits 3 seconds, then rechecks both slots and stats

If any check detects activity, the unload is aborted and the idle timer resets.

### Hot-Reload

The config file is re-read every 10 seconds (cached between checks). When a change is detected:

- New keepalive durations take effect immediately
- If the timeout was increased, a pending unload is aborted
- If a model's keepalive was set to `0` or removed, tracking stops
- Changes are logged with timestamps:
  ```
  2026-04-06 12:34:56.123 [Info] (IdleWatchdog) 'Qwen3.5-4B-GGUF' keep_alive changed: 2m -> 5m
  ```

### Port Discovery

The llama-server runs on an internal port that isn't directly exposed by Lemonade. The watchdog discovers it by parsing `/proc/net/tcp` inside the container, filtering out known ports (Lemonade router, websocket). The discovered port is cached and invalidated when a model is unloaded.

## GPU Support

This image is configured for AMD ROCm GPUs. To use a different GPU backend, adjust the environment variables in `docker-compose.yml`:

- **ROCm (AMD)**: Set `LEMONADE_LLAMACPP=rocm` and pass through `/dev/kfd` and `/dev/dri`
- **Vulkan (generic GPU)**: Set `LEMONADE_LLAMACPP=vulkan`
- **CPU only**: Remove GPU device mounts, Lemonade falls back to CPU automatically

### Custom llama-server Binary

To use your own llama-server build (e.g., a ROCm-optimized build):

```yaml
volumes:
  - ./llamacpp:/backends
environment:
  - LEMONADE_LLAMACPP_ROCM_BIN=/backends/rocm/llama-server
```

## Logs

The watchdog logs meaningful events only — it's silent during normal polling:

```
2026-04-06 12:34:56.123 [Info] (IdleWatchdog) starting (version: a1b2c3d4)
2026-04-06 12:34:56.124 [Info] (IdleWatchdog) check interval: 30s, pre-unload wait: 3s
2026-04-06 12:34:56.125 [Info] (IdleWatchdog) config file search paths:
2026-04-06 12:34:56.125 [Info] (IdleWatchdog)   /root/.cache/lemonade/keepalive_options.json (found)
2026-04-06 12:34:56.126 [Info] (IdleWatchdog) loaded keepalive config:
2026-04-06 12:34:56.126 [Info] (IdleWatchdog)   _default: 10m
2026-04-06 12:34:56.126 [Info] (IdleWatchdog)   Qwen3.5-35B-A3B-GGUF: 30m
2026-04-06 12:34:56.127 [Info] (IdleWatchdog) tracking 'Qwen3.5-4B-GGUF' (keep_alive: 10m)
2026-04-06 12:35:26.128 [Info] (IdleWatchdog) 'Qwen3.5-4B-GGUF' idle 30s, unload in 2m
2026-04-06 12:36:00.129 [Info] (IdleWatchdog) 'Qwen3.5-4B-GGUF' idle 60s, unload in 1m
2026-04-06 12:37:00.130 [Info] (IdleWatchdog) 'Qwen3.5-4B-GGUF' idle 120s, unloading... (keep_alive: 10m)
2026-04-06 12:37:00.131 [Info] (IdleWatchdog)   'Qwen3.5-4B-GGUF' all clear, sending unload request
2026-04-06 12:37:00.132 [Info] (IdleWatchdog)   'Qwen3.5-4B-GGUF' unloaded successfully
```

### Log Levels

- **Startup**: Shows version hash, check interval, config paths, and loaded configuration
- **Idle tracking**: Logs when a model starts idling and periodic progress updates
- **Activity detection**: Resets idle timer when new requests arrive
- **Unload events**: Pre-unload verification, aborts if activity detected, or success message
- **Warnings**: Shows when llama-server port discovery or slot queries fail

## Upstream

This project adds keepalive functionality that Lemonade Server doesn't have natively. The infrastructure for it exists in Lemonade (per-model config via `recipe_options.json`, `last_use` tracking, `/api/v1/unload` endpoint) — it just needs a `keep_alive` field and idle eviction logic built in. If you'd like to see this upstream, consider voicing support on the [Lemonade GitHub](https://github.com/lemonade-sdk/lemonade).

## License

Apache 2.0 — same as Lemonade Server.

## Acknowledgments

Huge thanks to the [Lemonade Team](https://github.com/lemonade-sdk/lemonade) for building what the AMD local AI community desperately needed.
