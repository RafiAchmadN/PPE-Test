#!/usr/bin/env bash
# Generate sertifikat self-signed untuk proxy TLS lokal/testing (lihat
# proxy/nginx.conf dan docs/SAAS_READINESS_AUDIT.md §2/§4).
#
# HANYA untuk testing lokal/LAN — browser akan menampilkan peringatan
# "Not Secure" karena sertifikat tidak ditandatangani CA terpercaya.
# Untuk produksi/demo publik, timpa proxy/certs/cert.pem + key.pem dengan
# sertifikat asli (Let's Encrypt / CA internal perusahaan).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="$SCRIPT_DIR/../proxy/certs"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
    echo "Sertifikat sudah ada di $CERT_DIR — hapus dulu file lama jika ingin generate ulang."
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
    -days 825 \
    -subj "//CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "Sertifikat self-signed dibuat di $CERT_DIR"
echo "Jalankan 'docker compose -f docker-compose.prod.yml up -d' setelah ini."
