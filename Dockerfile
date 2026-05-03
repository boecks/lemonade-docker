FROM ghcr.io/lemonade-sdk/lemonade-server:v10.3.0

# Runtime dep for the watchdog
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
    && rm -rf /var/lib/apt/lists/*

COPY auto_unload.py /opt/auto_unload.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]