FROM fedora:45
ARG LEMONADE_VERSION=10.3.0

RUN dnf install -y \
        --setopt=install_weak_deps=False \
        --setopt=tsflags=nodocs \
        ca-certificates curl python3 \
    && dnf install -y \
        --setopt=tsflags=nodocs \
        "https://github.com/lemonade-sdk/lemonade/releases/download/v${LEMONADE_VERSION}/lemonade-server-${LEMONADE_VERSION}.x86_64.rpm" \
    && dnf clean all \
    && rm -rf /var/cache/dnf /var/log/dnf* /usr/share/doc /usr/share/man /usr/share/info

ENV HF_HOME=/models

COPY auto_unload.py /opt/auto_unload.py
COPY entrypoint.sh  /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:13305/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]