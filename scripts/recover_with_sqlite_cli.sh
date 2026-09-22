#!/bin/bash
# Pemulihan logging.db pakai sqlite3 CLI ".recover" (raw per-page scan --
# jauh lebih robust untuk korupsi tersebar daripada scripts/recover_db.py,
# lihat perbandingan di docstring file itu: 99.99% vs 35% pada uji yang sama).
#
# Dijalankan di DALAM container bantuan sementara (python:3.11-slim), BUKAN
# image ppe-backend -- supaya tidak perlu rebuild image utama yang sedang
# proses. logging.db ASLI tidak pernah ditulis, cuma dibaca.
cd /work || exit 1

echo "[1/4] Install sqlite3 CLI di container bantuan..."
apt-get update -qq && apt-get install -y -qq sqlite3 >/dev/null || exit 1

echo "[2/4] Menjalankan .recover terhadap logging.db (baca saja, tidak diubah)..."
# TIDAK pakai "set -e" di sini dengan sengaja -- .recover pada file yang
# BENAR-BENAR korup wajar keluar dengan exit code non-nol walau tetap
# berhasil mengekstrak banyak baris; kalau script berhenti paksa di sini,
# hasil ekstraksi yang sudah didapat malah tidak sempat dipakai sama sekali.
sqlite3 logging.db '.recover' > /tmp/recovered.sql 2>/tmp/recover_errors.txt
echo "  -> $(wc -l < /tmp/recovered.sql) baris SQL berhasil diekstrak"
if [ -s /tmp/recover_errors.txt ]; then
  echo "  -- stderr .recover (informasional, boleh diabaikan kalau hasil akhir masuk akal) --"
  cat /tmp/recover_errors.txt
fi
if [ ! -s /tmp/recovered.sql ]; then
  echo "GAGAL TOTAL: .recover tidak menghasilkan output sama sekali. logging.db mungkin rusak di luar yang bisa ditangani .recover."
  exit 1
fi

echo "[3/4] Membangun logging_recovered.db dari hasil ekstraksi..."
rm -f logging_recovered.db
# sqlite_sequence itu tabel internal SQLite (auto-terkelola) -- .recover
# suka ikut nulis CREATE TABLE eksplisit untuknya yang bikin import gagal.
sed '/CREATE TABLE sqlite_sequence/d' /tmp/recovered.sql | sqlite3 logging_recovered.db
if [ ! -s logging_recovered.db ]; then
  echo "GAGAL: logging_recovered.db tidak terbentuk. Cek /tmp/recovered.sql di dalam container ini manual."
  exit 1
fi

echo "[4/4] Ringkasan hasil pemulihan:"
sqlite3 logging_recovered.db "SELECT 'data: ' || COUNT(*) FROM data;"
sqlite3 logging_recovered.db "SELECT 'cameras: ' || COUNT(*) FROM cameras;"
sqlite3 logging_recovered.db "SELECT 'users: ' || COUNT(*) FROM users;"
sqlite3 logging_recovered.db "SELECT 'app_settings: ' || COUNT(*) FROM app_settings;"
echo
echo "SELESAI -> logging_recovered.db dibuat di folder ini."
echo "logging.db ASLI tidak diubah sama sekali -- masih ada, masih (masih) korup."
echo "Bandingkan jumlah baris di atas dengan perkiraan kamu sebelum lanjut ke langkah swap."
