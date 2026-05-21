FROM ghcr.io/lemonade-sdk/lemonade-server:v10.5.1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
    && rm -rf /var/lib/apt/lists/*

ENV HF_HOME=/models
ENV LEMONADE_CACHE_DIR=/var/lib/lemonade/.cache/lemonade

COPY auto_unload.py /opt/auto_unload.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]