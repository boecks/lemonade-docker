FROM ubuntu:24.04

ARG LEMONADE_VERSION=10.0.0

ENV DEBIAN_FRONTEND=noninteractive

# Runtime dependencies only — ROCm comes from the host via /dev/kfd + /dev/dri,
# the .deb bundles its own ROCm libs
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgomp1 \
        libatomic1 \
        moreutils \
        python3 \
    && rm -rf /var/lib/apt/lists/*

# Install Lemonade Server (includes web app + binary)
RUN curl -L -o /tmp/lemonade.deb \
        "https://github.com/lemonade-sdk/lemonade/releases/download/v${LEMONADE_VERSION}/lemonade-server_${LEMONADE_VERSION}_amd64.deb" \
    && apt-get update \
    && apt-get install -y /tmp/lemonade.deb \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /tmp/* /var/lib/apt/lists/*

# Model storage and llama backend (mount from host)
VOLUME ["/models", "/usr/local/share/lemonade-server/llama"]

EXPOSE 8000

# Lemonade core config
ENV HF_HOME=/models
ENV LEMONADE_HOST=0.0.0.0
ENV LEMONADE_PORT=8000
ENV LEMONADE_LLAMACPP=rocm

# Idle model watchdog — reads config from /root/.cache/lemonade/keepalive_options.json
COPY auto_unload.py /opt/auto_unload.py

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/live || exit 1

ENTRYPOINT ["/entrypoint.sh"]