#!/bin/sh
# Maakt een self-signed certificaat aan als er nog geen staat in /certs.
# Wordt door het officiele nginx-entrypoint uitgevoerd voordat nginx start.
# Mount /certs als volume, dan blijft het certificaat bewaard en hoeft de
# browserwaarschuwing maar een keer weggeklikt te worden.
set -e

CERT_DIR=/certs

if [ -s "${CERT_DIR}/cert.pem" ] && [ -s "${CERT_DIR}/key.pem" ]; then
    echo "supersplat: bestaand certificaat in ${CERT_DIR} gebruiken"
    exit 0
fi

echo "supersplat: self-signed certificaat aanmaken in ${CERT_DIR}"
mkdir -p "${CERT_DIR}"
openssl req -x509 -nodes \
    -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
    -days 3650 \
    -subj "/CN=supersplat" \
    -keyout "${CERT_DIR}/key.pem" \
    -out "${CERT_DIR}/cert.pem"
chmod 600 "${CERT_DIR}/key.pem"
