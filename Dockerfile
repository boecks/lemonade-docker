FROM fedora:45
ARG LEMONADE_VERSION=10.3.0

# Runtime deps not pulled in by the lemonade-server RPM itself.
# moreutils for `ts` (timestamps in logs, if your watchdog uses it).
# python3 for the auto_unload.py watchdog.
# curl for the healthcheck.
# ca-certificates implicit on Fedora but harmless to be explicit.
RUN dnf install -y --setopt=install_weak_deps=False \
        ca-certificates \
        curl \
        moreutils \
        python3 \
    && dnf clean all

# Install the RPM directly from GitHub releases. dnf resolves runtime deps
# (libwebsockets, libgomp, etc.) from Fedora repos automatically. The RPM's
# postinst script runs and creates the expected symlinks.
RUN dnf install -y \
      "https://github.com/lemonade-sdk/lemonade/releases/download/v${LEMONADE_VERSION}/lemonade-server-${LEMONADE_VERSION}.x86_64.rpm" \
    && dnf clean all

ENV HF_HOME=/models
ENV LEMONADE_PORT=13305
ENV LEMONADE_CACHE_DIR=/var/lib/lemonade/.cache/lemonade

COPY auto_unload.py /opt/auto_unload.py
COPY entrypoint.sh  /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:13305/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]