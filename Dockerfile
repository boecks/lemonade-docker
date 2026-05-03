FROM ubuntu:26.04
ARG LEMONADE_VERSION=10.3.0
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgomp1 \
        libatomic1 \
        moreutils \
        python3 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/lemonade.tar.gz \
      "https://github.com/lemonade-sdk/lemonade/releases/download/v${LEMONADE_VERSION}/lemonade-embeddable-${LEMONADE_VERSION}-ubuntu-x64.tar.gz" \
    && mkdir -p /opt/lemonade \
    && tar -xzf /tmp/lemonade.tar.gz -C /opt/lemonade --strip-components=1 \
    && rm /tmp/lemonade.tar.gz \
    && ln -s /opt/lemonade/lemond    /usr/local/bin/lemond \
    && ln -s /opt/lemonade/lemonade  /usr/local/bin/lemonade

RUN mkdir -p /opt/lemonade/resources/static \
    && curl -fsSL -o /opt/lemonade/resources/static/index.html \
        "https://raw.githubusercontent.com/lemonade-sdk/lemonade/v${LEMONADE_VERSION}/src/cpp/resources/static/index.html" \
    && curl -fsSL -o /opt/lemonade/resources/static/favicon.ico \
        "https://raw.githubusercontent.com/lemonade-sdk/lemonade/v${LEMONADE_VERSION}/src/cpp/resources/static/favicon.ico"

ENV HF_HOME=/models
ENV LEMONADE_PORT=13305
ENV LEMONADE_CACHE_DIR=/var/lib/lemonade/.cache/lemonade

COPY auto_unload.py /opt/auto_unload.py
COPY entrypoint.sh  /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:13305/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]