# lemonade-docker

An unofficial container image for [Lemonade Server](https://github.com/lemonade-sdk/lemonade) with a side-car watchdog that unloads idle models on a configurable per-model schedule.

Lemonade keeps loaded models resident until you explicitly unload them. That's the right default for a desktop install, but if you serve models from a workstation or a small GPU box, you usually want a few of them to drop themselves after a quiet period so VRAM stays available for whichever one you actually need next. This image bundles a small Python watchdog that does exactly that, leaving everything else about Lemonade untouched.

> [!NOTE]
> This is a community project. It is not affiliated with or endorsed by AMD or the Lemonade SDK team.

## What's in the image

- **Lemonade Server** installed from the official [`ppa:lemonade-team/stable`](https://launchpad.net/~lemonade-team/+archive/ubuntu/stable) PPA, pinned at build time via the `LEMONADE_VERSION` build arg.
- **`auto_unload.py`** — a standalone Python script with no dependencies outside the standard library. It polls Lemonade's HTTP API for loaded models and llama-server's `/slots` endpoint for actual inference activity, then issues unload requests when a model has been idle long enough. Activity detection is conservative: a model is only unloaded after multiple checks confirm no slot is processing and the configured timeout has elapsed.

The watchdog is opt-in per model. Without configuration it does nothing, exactly matching upstream Lemonade behavior.

## Quick start

```bash
git clone https://github.com/<you>/lemonade-docker
cd lemonade-docker
docker compose up -d
```

Lemonade is then reachable at `http://localhost:13305` (the v10+ default port). Logs stream to `docker logs -f lemonade-server`.

To enable idle unloading for a model, drop a `keepalive_options.json` file into the cache volume — see [Configuration](#configuration) below.

## docker-compose.yml

```yaml
services:
  lemonade:
    build:
      context: .
      args:
        LEMONADE_VERSION: 10.1.0
    container_name: lemonade-server
    ports:
      - "13305:13305"  # HTTP API
      - "9000:9000"    # WebSocket logs
    volumes:
      - ./models:/models
      - ./llama:/usr/local/share/lemonade-server/llama
      - ./lemonade-cache:/var/lib/lemonade/.cache/lemonade
    devices:
      - /dev/kfd
      - /dev/dri
    group_add:
      - video
      - render
    restart: unless-stopped
```

The bind mount on `./lemonade-cache` is what makes `keepalive_options.json` editable from the host. It also persists Lemonade's own `config.json` across container rebuilds, so anything you change with `lemonade config set ...` survives.

If you don't need ROCm, drop the `devices` and `group_add` blocks and let the `llamacpp` backend default to `auto`.

## Configuration

### Lemonade itself

In v10+, all of Lemonade's configuration lives in a single `config.json` file inside the cache directory. With the bind mount above, that file is at `./lemonade-cache/config.json` on the host. You can either edit it directly (and restart the container) or use the official CLI without restarting:

```bash
docker exec lemonade-server lemonade config            # show current config
docker exec lemonade-server lemonade config set llamacpp.backend=rocm
docker exec lemonade-server lemonade config set port=8000
```

See the [upstream configuration guide](https://github.com/lemonade-sdk/lemonade/blob/main/docs/server/configuration.md) for the full set of keys.

### Idle unload watchdog

The watchdog reads `keepalive_options.json` from the same cache directory. The file is **completely optional** — without it, the watchdog runs but unloads nothing, matching upstream's "loaded means loaded" behavior.

#### Minimal example

```json
{
  "Qwen3.5-4B-GGUF": { "keep_alive": "5m" },
  "Qwen3.5-35B-A3B-GGUF": { "keep_alive": "30m" }
}
```

Only the two models listed are tracked. Any other model that gets loaded is left alone forever, just like upstream.

#### With a global default

If you want most models to share the same timeout and only override a few, use the special `_global` key:

```json
{
  "_global": { "keep_alive": "10m" },
  "Qwen3.5-35B-A3B-GGUF": { "keep_alive": "1h" },
  "Llama-3.2-1B-Instruct-Hybrid": { "keep_alive": "-1" }
}
```

With `_global` set, **every** loaded model gets a 10-minute idle timeout unless it has its own entry. The big Qwen overrides to 1h; the small Llama overrides to never unload.

`_global` is opt-in. If you don't want a global default, leave it out and only the models you list will be tracked.

#### Duration syntax

| Value | Meaning |
|-------|---------|
| `"30s"` / `"30"` | 30 seconds |
| `"5m"` | 5 minutes |
| `"1h"` | 1 hour |
| `"0"` | unload on next check cycle (immediate) |
| `"-1"` | never unload (keep loaded indefinitely) |

The minimum effective timeout is `2 * LEMONADE_CHECK_INTERVAL` (60 seconds by default). Smaller values are clamped and a warning is logged.

#### Sharing the file with Lemonade's recipe options

If Lemonade tolerates unknown keys in `recipe_options.json`, you can put `keep_alive` directly inside your existing recipe entries instead of maintaining a separate file:

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

The watchdog reads `recipe_options.json` as a fallback when `keepalive_options.json` is absent. Use whichever layout you prefer.

### Hot reload

The watchdog re-reads its config file every 10 seconds, so you can change timeouts without restarting anything. Edit `./lemonade-cache/keepalive_options.json` on the host and the next idle check picks up the change. Adding, removing, and modifying entries are all hot-reloadable.

## Environment variables

The watchdog respects a small set of optional variables. Lemonade itself migrated almost all of its env vars into `config.json` in v10.1; only `LEMONADE_API_KEY` and `HF_TOKEN` remain on the Lemonade side.

| Variable | Default | Purpose |
|----------|---------|---------|
| `LEMONADE_PORT` | `13305` | Port the watchdog uses to talk to Lemonade. Lemonade itself reads its port from `config.json`; this only affects the watchdog. |
| `LEMONADE_CACHE_DIR` | `/var/lib/lemonade/.cache/lemonade` | Where the watchdog looks for `keepalive_options.json`. |
| `LEMONADE_CHECK_INTERVAL` | `30` | How often (seconds) the watchdog polls for idle models. |
| `LEMONADE_KEEPALIVE_CONFIG` | unset | Explicit path to a config file. Highest priority in the search list. |
| `LEMONADE_API_KEY` | unset | Forwarded to Lemonade for API authentication. |
| `HF_TOKEN` | unset | Forwarded to Lemonade for gated model downloads. |

## How idle detection works

The watchdog uses two independent signals to decide whether a model is in use:

1. **Lemonade's `last_use` timestamp** for each loaded model, retrieved from `/api/v1/health`. Changes here indicate a request hit Lemonade since the last check.
2. **llama-server's `/slots` endpoint**, which exposes per-slot `is_processing` flags. This catches in-flight inference that hasn't yet updated `last_use` (long generations, streaming responses, etc).

Before unloading, the watchdog runs a three-stage safety check: confirm no slot is currently processing, re-fetch Lemonade health to make sure `last_use` hasn't moved, then sleep briefly and re-check both. Any sign of activity aborts the unload and resets the idle timer. This conservatism is intentional — false positives that interrupt a streaming response are much worse than holding a model in memory for an extra check cycle.

The llama-server port is discovered automatically by scanning localhost listeners and probing each candidate for `/slots`. No assumption is made about which port llama-server will pick; it has been observed to walk forward (8001, 8002, ...) across reloads in v10.1.

## Limitations and gotchas

- **llama-server-backed models only.** The slot-based activity check only works for models served by llama.cpp. Models served by other backends (whisper, sd, kokoro, etc.) fall back to `last_use` polling alone, which is less precise.
- **No multi-model unload coordination.** Each loaded model is tracked independently. If two models are loaded simultaneously, they may unload in either order based on their own idle timers.
- **Inside the container only.** The `/proc/net/tcp` scan looks at listeners inside the container's network namespace. If you run Lemonade with `network_mode: host`, the scan will see every listener on the host and may misidentify the llama-server port. The `/slots` probe usually disambiguates this correctly, but it's not guaranteed.
- **Permissions on the bind mount.** Depending on how the deb package configures Lemonade's user inside the container, you may need to `chown` the host `./lemonade-cache` directory so Lemonade can write `config.json`. If the container fails to start with permission errors, that's almost always the cause.

## Building

```bash
docker compose build
# or
docker build --build-arg LEMONADE_VERSION=10.1.0 -t lemonade-server:10.1.0 .
```

The Dockerfile is intentionally short — it installs the PPA, copies in two files, and exits. Everything substantive is in `auto_unload.py` and the upstream package.

## Contributing

Issues and PRs welcome. The watchdog is small enough that a fix is usually a few lines; please include a snippet of the log output that shows the problem if you can.

If you find a bug that's actually in upstream Lemonade rather than in this image, please report it at [lemonade-sdk/lemonade](https://github.com/lemonade-sdk/lemonade) instead — the maintainers there are responsive and the project moves fast.


## License

Apache License 2.0. See [LICENSE](./LICENSE).

Lemonade Server is also Apache 2.0, licensed by AMD; see the [upstream repository](https://github.com/lemonade-sdk/lemonade) for details.