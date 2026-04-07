FROM ubuntu:24.04
ARG LEMONADE_VERSION=10.1.0
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgomp1 \
        libatomic1 \
        moreutils \
        python3 \
        software-properties-common \
    && rm -rf /var/lib/apt/lists/*

RUN add-apt-repository -y ppa:lemonade-team/stable \
    && apt-get update \
    && apt-get install -y lemonade-server=${LEMONADE_VERSION}* \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*

# Model storage and llama backend (mount from host)
VOLUME ["/models", "/usr/local/share/lemonade-server/llama"]

# Lemonade cache dir on Linux — holds config.json and keepalive_options.json
VOLUME ["/var/lib/lemonade/.cache/lemonade"]

# Upstream defaults: 13305 = HTTP API, 9000 = websocket logs
EXPOSE 13305 9000

ENV HF_HOME=/models
# LEMONADE_API_KEY / HF_TOKEN: set at runtime if needed

# Watchdog needs to know where Lemonade lives and where its config is.
# Default port matches upstream; override via compose if you remap.
ENV LEMONADE_PORT=13305
ENV LEMONADE_CACHE_DIR=/var/lib/lemonade/.cache/lemonade

COPY auto_unload.py /opt/auto_unload.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:13305/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]