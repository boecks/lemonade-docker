FROM ubuntu:24.04
ARG LEMONADE_VERSION=10.3.0
ENV DEBIAN_FRONTEND=noninteractive

# Runtime deps + rpm2cpio for extraction.
# rpm2cpio is provided by the rpm2cpio package on noble.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        cpio \
        curl \
        rpm2cpio \
        libgomp1 \
        libatomic1 \
        moreutils \
        python3 \
    && rm -rf /var/lib/apt/lists/*

# Fetch the RPM from GitHub releases and extract its payload onto the
# filesystem. RPM payload uses absolute paths (./opt/..., ./usr/...) which
# cpio recreates verbatim. We strip the leading "." so files land at
# /opt/... and /usr/... as the packaging team intended.
RUN curl -fsSL -o /tmp/lemonade.rpm \
      "https://github.com/lemonade-sdk/lemonade/releases/download/v${LEMONADE_VERSION}/lemonade-server-${LEMONADE_VERSION}.x86_64.rpm" \
    && cd / \
    && rpm2cpio /tmp/lemonade.rpm | cpio -idmv \
    && rm /tmp/lemonade.rpm

# After extraction, the apt-installed packages we no longer need can go.
# rpm2cpio + cpio were just for unpacking, and they pulled in some perl/python
# bits as deps. Trim them to keep the image smaller.
RUN apt-get purge -y rpm2cpio cpio \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

ENV HF_HOME=/models
ENV LEMONADE_PORT=13305
ENV LEMONADE_CACHE_DIR=/var/lib/lemonade/.cache/lemonade

COPY auto_unload.py /opt/auto_unload.py
COPY entrypoint.sh  /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:13305/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]