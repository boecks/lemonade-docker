FROM ubuntu:24.04

ARG LEMONADE_VERSION=9.4.1
ENV DEBIAN_FRONTEND=noninteractive

# Laufzeit-Deps: ROCm-fähige Vulkan-Treiber + GoMP (OpenMP)
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    libgomp1 \
    libvulkan1 \
    mesa-vulkan-drivers \
    && rm -rf /var/lib/apt/lists/*

# .deb herunterladen und installieren – enthält WebApp + lemonade-server binary
RUN curl -L -o /tmp/lemonade.deb \
    "https://github.com/lemonade-sdk/lemonade/releases/download/v${LEMONADE_VERSION}/lemonade-server_${LEMONADE_VERSION}_amd64.deb" \
    && apt-get update \
    && apt-get install -y /tmp/lemonade.deb \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /tmp/* /var/lib/apt/lists/*

# Pfade
VOLUME ["/models", "/usr/local/share/lemonade-server/llama"]
EXPOSE 8000

# Umgebung
ENV HF_HOME=/models
ENV LEMONADE_HOST=0.0.0.0
ENV LEMONADE_PORT=8000
# ROCm-Backend für RDNA4 / RX 9700 AI Pro
ENV LEMONADE_LLAMACPP=rocm
# Kontext-Größe – anpassen nach Bedarf (4k=4096, 32k=32768, 128k=131072)
ENV LEMONADE_CTX_SIZE=8192

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/live || exit 1

ENTRYPOINT ["lemonade-server"]
CMD ["serve"]