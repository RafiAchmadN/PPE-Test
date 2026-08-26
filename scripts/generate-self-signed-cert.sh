#!/usr/bin/env bash
# Generate sertifikat self-signed untuk proxy TLS internal (lihat
# proxy/nginx.conf dan docs/SAAS_READINESS_AUDIT.md §2/§4).
#
# Cert ini cuma untuk hop internal nginx-gateway <-> ppe-proxy (server_name
# nginx.conf catch-all "_", jadi hostname di cert tidak divalidasi browser
# pengguna — mereka lihat cert asli Let's Encrypt milik nginx-gateway).
# Browser TETAP menampilkan peringatan "Not Secure" kalau proxy ini diakses
# langsung (tanpa lewat nginx-gateway) karena sertifikatnya tidak
# ditandatangani CA terpercaya. Untuk produksi/demo publik yang expose proxy
# ini langsung ke internet, timpa proxy/certs/cert.pem + key.pem dengan
# sertifikat asli (Let's Encrypt / CA internal perusahaan).
#
# Override domain default lewat env var: CERT_DOMAIN=lain.domain.id bash scripts/generate-self-signed-cert.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="$SCRIPT_DIR/../proxy/certs"
DOMAIN="${CERT_DOMAIN:-project.insamo.id}"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
    echo "Sertifikat sudah ada di $CERT_DIR — hapus dulu file lama jika ingin generate ulang."
    exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" \
    -days 825 \
    -subj "//CN=$DOMAIN" \
    -addext "subjectAltName=DNS:$DOMAIN,DNS:localhost,IP:127.0.0.1"

echo "Sertifikat self-signed dibuat di $CERT_DIR"
echo "Jalankan 'docker compose -f docker-compose.prod.yml up -d' setelah ini."
