FROM ubuntu:24.04
ARG LEMONADE_VERSION=10.3.0
# Signing key fingerprint for the lemonade-team/stable PPA.
# Get this from: https://launchpad.net/~lemonade-team/+archive/ubuntu/stable
# (expand "Technical details about this PPA" → "Signing key")
ARG LEMONADE_PPA_KEY_FP=881CF4B40B0BFA288D6776E83BF36CFA0BD50AEC
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        libgomp1 \
        libatomic1 \
        moreutils \
        python3 \
    && rm -rf /var/lib/apt/lists/*

# Set up the PPA manually — no add-apt-repository, no Launchpad API call.
# Fetch the key directly from keyserver.ubuntu.com with a hard timeout.
RUN install -d /etc/apt/keyrings \
    && curl -fsSL --max-time 30 \
        "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x${LEMONADE_PPA_KEY_FP}" \
        | gpg --dearmor -o /etc/apt/keyrings/lemonade-team.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/lemonade-team.gpg] https://ppa.launchpadcontent.net/lemonade-team/stable/ubuntu noble main" \
        > /etc/apt/sources.list.d/lemonade-team.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        lemonade-server=${LEMONADE_VERSION}* \
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