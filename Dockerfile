# Ethos Aegis — publishable runtime image
# ghcr.io/deontewattsv1/ethos-aegis
#
# The previous multi-stage file copied a root setup.py and ethos_aegis/
# package that are not at the repository root, so the image could not build.
# This image packages the Node SDK, which is the runtime the old file
# actually tried to start.

FROM node:20-bookworm-slim AS runtime

WORKDIR /app
COPY sdk/node/package.json sdk/node/package.json
COPY sdk/node/src sdk/node/src
COPY sdk/node/types sdk/node/types
COPY sdk/node/LICENSE sdk/node/LICENSE

RUN groupadd --gid 1001 aegis \
 && useradd --uid 1001 --gid aegis --shell /usr/sbin/nologin --create-home aegis \
 && chown -R aegis:aegis /app
USER aegis

ENV NODE_ENV=production \
    AEGIS_ENV=production
EXPOSE 8080
CMD ["node", "sdk/node/src/index.js"]

LABEL org.opencontainers.image.title="Ethos Aegis"
LABEL org.opencontainers.image.description="Sovereign Integrity Mesh — Node SDK runtime"
LABEL org.opencontainers.image.source="https://github.com/DeontewattsV1/Ethos-Aegis-"
LABEL org.opencontainers.image.url="https://github.com/DeontewattsV1/Ethos-Aegis-"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="Deonte Watts"
