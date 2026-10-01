# SuperSplat - Gaussian splat-editor, gebouwd uit de officiele broncode.
# Bron: https://github.com/playcanvas/supersplat (MIT)
# Versie wordt bij het bouwen meegegeven via SUPERSPLAT_REF (release-tag).
# Het renderen gebeurt in de browser; deze container serveert alleen statische bestanden.

ARG NODE_VERSION=22

########################################
# Stage 1: builder - bouwt dist/
########################################
FROM node:${NODE_VERSION}-bookworm-slim AS builder

ARG SUPERSPLAT_REF

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN test -n "${SUPERSPLAT_REF}" || (echo "SUPERSPLAT_REF is niet opgegeven" >&2 && exit 1) \
    && git clone --depth 1 --branch "${SUPERSPLAT_REF}" https://github.com/playcanvas/supersplat.git .

RUN npm ci --no-audit --no-fund \
    && npm run build

########################################
# Stage 2: runtime - nginx met alleen dist/
########################################
FROM nginx:stable-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /src/dist /usr/share/nginx/html

# Splats-map wordt hier alleen-lezen gemount en onder /splats/ geserveerd
RUN mkdir -p /splats

EXPOSE 80
