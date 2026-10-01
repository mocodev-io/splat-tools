# SuperSplat - Gaussian splat-editor, gebouwd uit de officiele broncode.
# Bron: https://github.com/playcanvas/supersplat (MIT)
# Versie wordt bij het bouwen meegegeven via SUPERSPLAT_REF (release-tag).
# Het renderen gebeurt in de browser; deze container serveert alleen statische bestanden.
# Geserveerd via HTTPS met een self-signed certificaat: browsers geven WebGPU
# alleen vrij op HTTPS (of localhost).

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

# openssl voor het aanmaken van het self-signed certificaat
RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY 10-selfsigned-cert.sh /docker-entrypoint.d/10-selfsigned-cert.sh
RUN chmod +x /docker-entrypoint.d/10-selfsigned-cert.sh

COPY --from=builder /src/dist /usr/share/nginx/html

# /splats: splats-map, alleen-lezen gemount en onder /splats/ geserveerd
# /certs:  certificaat, als volume mounten zodat het bewaard blijft
RUN mkdir -p /splats /certs

EXPOSE 443
