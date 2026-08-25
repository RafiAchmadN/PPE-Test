# Audit Kesiapan Komersialisasi — MAPPER

> Model target: **appliance on-prem per pelanggan** (1 instance = 1 pelanggan/site),
> dijual sebagai produk berlisensi dan di-deploy di server pelanggan sendiri.
> Bukan multi-tenant cloud SaaS — dokumen ini TIDAK membahas isolasi data
> lintas-tenant, billing, atau provisioning otomatis multi-pelanggan.
>
> Status: dokumen audit — **belum ada perubahan kode**. Prioritas P0/P1/P2 di
> bagian akhir perlu dikonfirmasi sebelum implementasi dimulai.

---

## 1. Ringkasan Eksekutif

MAPPER saat ini adalah **prototipe akademik yang berfungsi dengan baik secara
fungsional** (deteksi APD real-time, mAP@50 97,6%, dashboard React yang rapi),
tapi arsitekturnya masih di level "jalan di laptop developer/demo internal",
bukan "aman dipasang tanpa pengawasan di jaringan pelanggan selama berbulan-bulan".

Tiga risiko terbesar sebelum bisa dijual:

1. **Server produksi belum production-grade** — backend berjalan di atas
   development server Werkzeug (`app.run()`), tanpa TLS, tanpa reverse proxy.
   Ini titik kegagalan/keamanan paling mendasar untuk produk yang dipasang di
   jaringan pelanggan (kantor/pabrik), apalagi jika nanti diakses dari luar
   jaringan lokal.
2. **Kebocoran storage tak terbatas** — bug retensi (lihat §7) membuat disk
   pasti penuh cepat atau lambat di deployment jangka panjang, dan riwayat git
   repo pernah menyertakan `logging.db` asli (password hash + data pelanggaran)
   — perlu dibersihkan sebelum repo ini jadi basis produk yang didistribusikan.
3. **Tidak ada jaring pengaman operasional** — tanpa backup otomatis, tanpa
   monitoring/alerting, tanpa audit log, satu kegagalan disk/proses di lokasi
   pelanggan berarti kehilangan data pelanggaran permanen tanpa ada yang tahu.

Tidak satupun dari ini butuh rombak arsitektur besar — semuanya bisa
diselesaikan dengan mengeraskan (harden) yang sudah ada, cocok dengan model
appliance single-tenant yang dipilih.

---

## 2. Temuan Keamanan

| # | Temuan | Dampak | Severity |
|---|--------|--------|----------|
| S1 | `Dockerfile` menjalankan `python app_web.py` → Werkzeug dev server (`app.run(..., debug=False, threaded=True)`) sebagai server produksi | Dev server tidak dirancang untuk beban produksi/koneksi panjang (MJPEG), rentan resource exhaustion, tidak ada worker/proses terpisah | **Critical** |
| S2 | Tidak ada TLS/HTTPS di `docker-compose.prod.yml` — port 5000 & 8080 dipublish plaintext | Password login, session cookie, kredensial RTSP kamera, dan snapshot pelanggaran (berisi wajah pekerja) lewat jaringan tanpa enkripsi | **Critical** |
| S3 | `logging.db` (berisi hash password admin & data pelanggaran) pernah ter-*commit* ke git history (`git log --all -- logging.db` → 3 commit lama) meski sudah di-`.gitignore` sekarang | Siapa pun yang clone history lengkap repo bisa ambil file DB lama | **High** |
| S4 | Default password `admin123` tercetak di README & di-print ke stdout Docker log saat start, tanpa paksa ganti password di login pertama | Kredensial default adalah vektor serangan #1 untuk perangkat IoT/monitoring yang dipasang lalu dilupakan | **High** |
| S5 | Tidak ada rate limiting / lockout di `POST /api/auth/login` maupun `POST /api/auth/change-password` | Brute-force password tidak terdeteksi/terhambat sama sekali | **High** |
| S6 | Kredensial kamera (RTSP/DVRIP: `user:pass@host`) disimpan plaintext di kolom `cameras.url`, dan dikembalikan apa adanya oleh `GET /api/cameras` ke siapa pun yang login | Satu akun yang bocor = semua kredensial kamera pelanggan ikut bocor; tidak ada pemisahan "lihat status kamera" vs "lihat kredensial" | **High** |
| S7 | `SECRET_KEY` punya fallback hardcoded `'ppe-monitor-default-change-me-2026'` di source (baris 57) — meski `init_db()` menimpanya dengan key acak persisten saat startup normal | Kalau alur `init_db()` gagal/dilewati (mis. refactor mendatang), aplikasi diam-diam jalan dengan secret key publik yang ada di source code | **Medium** |
| S8 | Tidak ada CSRF token untuk endpoint state-changing (`POST/PUT/DELETE`); hanya mengandalkan `SameSite=Lax` cookie | `SameSite=Lax` tidak melindungi dari semua skenario CSRF (mis. navigasi top-level, subdomain nakal) | **Medium** |
| S9 | Tidak ada `MAX_CONTENT_LENGTH` di Flask & tidak ada validasi *magic bytes* pada `/api/videos/upload` (hanya cek ekstensi) | Upload file besar berulang → disk penuh (DoS); file dengan ekstensi `.mp4` tapi isi bukan video tidak divalidasi | **Medium** |
| S10 | Sesi login (`session.permanent = True`) tidak punya `PERMANENT_SESSION_LIFETIME` eksplisit (default Flask 31 hari), tidak ada idle-timeout, tidak ada "logout semua sesi" | Sesi yang dicuri/lupa logout di komputer bersama tetap valid berminggu-minggu | **Medium** |
| S11 | Tidak ada audit log (siapa mengubah kamera/setting/password, kapan) | Untuk produk yang menyangkut kepatuhan K3, ketiadaan jejak audit mengurangi kepercayaan & sulit investigasi insiden | **Medium** |
| S12 | Tidak ada security headers di `frontend/nginx.conf` (CSP, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, HSTS) | Permukaan serangan clickjacking/XSS tambahan yang mudah ditutup | **Low** |
| S13 | Tidak ada dependency vulnerability scanning (mis. `pip-audit`, `npm audit` di CI) — `requirements.txt` di-pin manual tanpa proses verifikasi otomatis | CVE pada dependency (Flask, ultralytics, dll.) tidak terpantau seiring waktu | **Low** |

**Catatan positif** yang sudah benar dan sebaiknya dipertahankan: password di-hash dengan `werkzeug.security` (bukan plaintext), `flask-cors` dibatasi origin eksplisit (bukan wildcard), nama file upload disanitasi mencegah path traversal, `send_from_directory` dipakai untuk serve foto bukti.

---

## 3. Temuan Database

| # | Temuan | Rekomendasi |
|---|--------|-------------|
| D1 | Tabel `data` tidak punya index pada `Tanggal` — query `/api/logs?start=&end=` dan cleanup retensi akan full-scan seiring data bertambah | Tambah `CREATE INDEX idx_data_tanggal ON data(Tanggal)` |
| D2 | `data.Lokasi` menyimpan **nama** kamera (TEXT), bukan `camera_id` (FK) | Jika kamera di-rename, log lama jadi tidak konsisten. Tambahkan kolom `camera_id INTEGER REFERENCES cameras(id)` sambil tetap simpan `Lokasi` sebagai label historis |
| D3 | Tidak ada mekanisme migrasi skema — `ALTER TABLE` inline di `init_db()` (pola "tambah kolom jika belum ada") akan makin rapuh seiring fitur baru | Untuk skala produk yang di-update berkala ke banyak pelanggan, pertimbangkan migration tool ringan (mis. penomoran versi skema manual atau `alembic` jika suatu saat pindah ke SQLAlchemy) |
| D4 | Tidak ada backup otomatis — `logging.db` + folder `data/violations/` hanya ada satu salinan di disk pelanggan | Jadwalkan backup harian (`sqlite3 .backup` API — aman dipakai bersamaan WAL — ke disk kedua/NAS), retensi backup terpisah dari retensi data live |
| D5 | SQLite cukup untuk 1 mesin appliance (WAL sudah aktif, `synchronous=NORMAL` sudah tepat untuk trade-off ini), TAPI belum diuji di beban nyata (banyak kamera menulis pelanggaran bersamaan + banyak user baca dashboard) | Masukkan ke rencana capacity test (§5) sebelum klaim kapasitas ke pelanggan; migrasi ke PostgreSQL hanya perlu jika hasil test menunjukkan bottleneck nyata — jangan migrasi preventif tanpa data |
| D6 | `exportdb.py` bergantung `PyQt5.QtSql` (GUI framework berat, tidak perlu untuk skrip headless) dan hardcode `mysql root / password kosong` — tidak dipakai dari aplikasi, jelas skrip coba-coba yang tertinggal | Ganti dengan tool ekspor berbasis `sqlite3` + `pandas`/`openpyxl` murni (tanpa PyQt5), atau jadikan endpoint admin "Export ke Excel/CSV" di dashboard yang sudah ada |

---

## 4. Temuan Infrastruktur & Deployment

| # | Temuan | Rekomendasi |
|---|--------|-------------|
| I1 | `docker-compose.prod.yml` mensyaratkan `networks.web: external: true` tapi tidak ada langkah `docker network create web` di README maupun di compose file | `docker compose up` di mesin baru **akan gagal** sampai user tahu harus buat network manual dulu. Ganti jadi network internal biasa (tanpa `external: true`) kecuali memang sengaja mau digabung reverse proxy eksternal — kalau begitu, dokumentasikan step-nya |
| I2 | Tidak ada `healthcheck:` di service manapun | Docker/orchestrator tidak tahu kalau backend "hidup tapi macet" (mis. inference worker deadlock); tambahkan healthcheck ke `/api/auth/status` atau endpoint `/healthz` baru yang tidak butuh login |
| I3 | Tidak ada resource limit (`mem_limit`/`deploy.resources.limits`) selain reservasi GPU | Proses yang leak memory (kamera banyak + inference lama) bisa menghabiskan RAM host tanpa batas | 
| I4 | Backend & frontend expose port langsung ke host tanpa reverse proxy TLS-terminating | Tambahkan Caddy/Nginx/Traefik sebagai satu-satunya entrypoint HTTPS (bisa pakai cert self-signed/internal CA untuk LAN, atau Let's Encrypt kalau expose ke internet) — backend tidak perlu publish port ke host sama sekali |
| I5 | Logging hanya `print()` ke stdout, tanpa rotasi/level/format terstruktur | Pindah ke modul `logging` Python dengan `RotatingFileHandler` atau biarkan stdout tapi dokumentasikan `docker logs --tail` + `logging` driver rotation di Docker daemon config, supaya disk tidak penuh oleh log |
| I6 | Tidak ada monitoring/alerting — status kamera online/offline sudah ada di API tapi tidak ada notifikasi proaktif | Tambahkan pengecekan berkala + notifikasi (email/webhook/Telegram) saat: kamera offline > N menit, disk > 80% terpakai, proses inference crash |
| I7 | Tidak ada CI (lint/test/build check) sebelum kode dikirim ke pelanggan | Minimal: GitHub Actions untuk `pip install` + `python -c "import app_web"` sanity check, `npm run build` frontend, dan (setelah ada) `pip-audit`/`npm audit` |
| I8 | GPU pinned ke CUDA 12.8/Blackwell (RTX 5060) di `Dockerfile` — belum tervalidasi di GPU lain atau CPU-only di beban produksi | Bagian dari rencana uji kompatibilitas (§5) sebelum deploy ke "PC yang lebih kuat" yang spec-nya mungkin beda |
| I9 | Tidak ada strategi update/rollback terdokumentasi untuk instance yang sudah live di pelanggan (README hanya `git pull` + rebuild) | Dokumentasikan prosedur: backup dulu → pull → build → migrate DB (jika ada) → up, plus cara rollback ke image sebelumnya kalau update bermasalah |

---

## 5. Rencana Uji Kompatibilitas

Karena OS target belum diputuskan, rencana ini mencakup kedua jalur:

### 5.1 Matriks OS × GPU
| OS | GPU | Yang diuji |
|----|-----|-----------|
| Linux native (Ubuntu 22.04/24.04) | NVIDIA (target: seri sama/lebih baru dari RTX 5060) | Install NVIDIA Container Toolkit, `docker compose up`, verifikasi `torch.cuda.is_available()==True` di container, throughput inference |
| Linux native | CPU-only (tanpa GPU/driver gagal) | Verifikasi fallback CPU di `load_model()`/`run_inference()` benar-benar terpakai tanpa crash, dan ukur FPS realistis untuk menentukan berapa kamera maksimum yang masih layak tanpa GPU |
| Windows 11 + Docker Desktop (WSL2) | NVIDIA | GPU passthrough WSL2 historically lebih rewel — verifikasi ulang di hardware baru sebelum janji dukungan Windows ke pelanggan |
| Windows 11 native (tanpa Docker) | NVIDIA | Jalur `python app_web.py` manual sesuai README §5 — pastikan tetap jalan sebagai alternatif kalau pelanggan tidak mau pakai Docker |

### 5.2 Fresh-install test
- Clone repo di mesin bersih (tanpa `.venv`/image lama), ikuti README apa adanya,
  catat setiap langkah manual yang *tidak* tertulis di README (mis. `docker
  network create web` — sudah ketahuan dari audit ini, lihat I1).
- Ulangi test ini setelah setiap perbaikan besar (regresi onboarding paling
  gampang lolos tanpa disadari).

### 5.3 Browser & perangkat
- Desktop: Chrome, Edge, Firefox versi terbaru.
- Tablet/mobile (umum dipakai pengawas lapangan pabrik): cek responsivitas
  dashboard React + kelancaran MJPEG stream di layar kecil/jaringan WiFi lemah.

### 5.4 Load & capacity test
- Simulasikan N kamera aktif (mulai dari jumlah realistis pelanggan pertama,
  naikkan bertahap) + M browser tab menonton `/api/stream/<id>` bersamaan +
  polling `/api/logs`/`/api/stats` — pakai `k6` atau `locust` untuk klien
  sintetis.
- Ukur: FPS efektif per kamera, latency dashboard, CPU/GPU/RAM host, titik di
  mana Werkzeug dev server (S1) mulai mengalami request antre/connection
  refused — ini jadi bukti kuantitatif kenapa S1 harus diperbaiki sebelum jual,
  dan jadi dasar klaim kapasitas resmi ("mendukung hingga X kamera") ke pelanggan.
- Ulangi setelah pindah ke WSGI server produksi (lihat roadmap P0) untuk
  membandingkan kapasitas sebelum/sesudah.

### 5.5 Resiliensi jaringan kamera
- Uji putus-sambung RTSP (cabut kabel/matikan kamera sementara) — kode retry
  (`_loop`, backoff eksponensial sampai 60s) sudah ada, verifikasi perilakunya
  di jaringan nyata yang flaky, bukan cuma di jaringan lab yang stabil.

---

## 6. Gap Produktisasi & Legal (non-kode)

- **Privasi data wajah pekerja**: sistem merekam & menyimpan snapshot wajah
  pekerja sebagai bukti pelanggaran. Ini data pribadi/biometrik menurut UU PDP
  (UU No. 27/2022) — pelanggan (perusahaan pembeli) perlu kebijakan
  retensi+consent yang jelas ke karyawannya, dan sebagai vendor, MAPPER perlu
  menyediakan kontrol teknis yang mendukung itu (retensi bisa diatur, ada cara
  hapus data atas permintaan, dll — berkaitan langsung dengan §7 di bawah).
- **Onboarding non-teknis**: instalasi saat ini butuh familiaritas Docker CLI +
  editing `docker-compose.yml`. Untuk dijual ke pelanggan industri (bukan tim
  IT), pertimbangkan installer script (`install.sh`/`install.ps1`) yang
  membungkus langkah-langkah README.
- **White-labeling**: logo HETI di `static/` hardcoded — kalau dijual ke banyak
  perusahaan dengan brand sendiri-sendiri, siapkan mekanisme ganti logo/nama
  produk tanpa sentuh kode.
- **Lisensi pemakaian**: belum ada mekanisme lisensi/proteksi (siapa pun yang
  punya akses source bisa deploy ulang tanpa batas). Ini keputusan bisnis, bukan
  wajib secara teknis — cukup dicatat sebagai keputusan yang perlu diambil
  sebelum distribusi luas.
- File-file sisa development di root repo (`exportdb.py`, `ipcamera.txt`) perlu
  dibersihkan/dipindah dari paket yang dikirim ke pelanggan agar terlihat
  profesional.

---

## 7. Manajemen Storage & Retensi Data

### 7.1 Bug yang ditemukan (perlu diperbaiki segera)
`_violation_writer()` di `app_web.py` (±baris 130–138) menghapus baris tabel
`data` yang `Tanggal < cutoff` setiap 1000 insert, **tapi tidak pernah
menghapus file JPEG di `data/violations/` yang menjadi rujukan kolom `Bukti`**.
Akibatnya:
- Disk akan terus terisi foto "yatim" (file tanpa row DB) tanpa batas, bahkan
  setelah cleanup "berhasil" menurut log.
- Karena trigger cleanup berbasis **hitungan insert** (bukan waktu), site
  dengan volume pelanggaran rendah bisa tidak pernah menjalankan cleanup sama
  sekali walau sudah bertahun-tahun jalan.

> **Status: SUDAH DIPERBAIKI** di `app_web.py` (`_violation_writer`) pada
> putaran implementasi P0 — retensi sekarang berjalan maksimal 1x/hari
> (berbasis tanggal, bukan hitungan insert) dan menghapus file JPEG bersamaan
> baris DB-nya.

### 7.2 Desain retensi yang direkomendasikan: 3 tingkat (hot/warm/archive)
Tujuannya: pelanggan tetap bisa **meninjau ulang bukti pelanggaran dari
beberapa hari/minggu lalu** dengan kualitas baik, tanpa disk pernah penuh,
dan tanpa kehilangan riwayat sepenuhnya secara tiba-tiba.

| Tingkat | Rentang waktu (default, bisa diatur) | Perlakuan |
|---------|---------------------------------------|-----------|
| **Hot** | 0–14 hari | JPEG kualitas capture asli (640px, quality 60 seperti sekarang) — untuk investigasi cepat, ditampilkan langsung di halaman Logs |
| **Warm** | 15–90 hari | Job harian men-downscale/re-compress foto di rentang ini (mis. turunkan ke ~50% resolusi atau quality lebih rendah) — tetap jelas untuk ditinjau visual, ukuran file jauh lebih kecil |
| **Archive** | 91 hari – batas retensi akhir (mis. 1 tahun, sesuai kebutuhan audit K3 pelanggan) | Dikemas jadi arsip terkompresi per bulan per kamera (`.zip`/`.tar.gz`) dan (jika tersedia) dipindah ke disk sekunder/NAS — tidak lagi ditampilkan langsung di UI tapi masih bisa direstore/dibuka manual saat dibutuhkan audit |
| **Hapus permanen** | > batas retensi akhir | Baris DB **dan** file/arsip dihapus bersamaan (memperbaiki bug §7.1) |

Semua angka hari di atas **harus jadi setting yang bisa diubah admin
pelanggan** (menu Settings yang sudah ada), bukan konstanta di kode —
kebutuhan tiap pelanggan beda (ada yang cukup 30 hari, ada yang wajib simpan
1 tahun untuk audit K3). Catatan implementasi P0: retensi 1-tingkat (hapus
langsung + file setelah `RETENTION_DAYS`) sudah aktif; tingkat warm/archive
di atas masih berstatus **rencana P1**, belum diimplementasikan.

### 7.3 Perubahan mekanisme cleanup
- Ganti trigger dari "tiap 1000 insert" menjadi **terjadwal berbasis waktu**
  (mis. job yang jalan sekali/hari di jam sepi) — konsisten terlepas dari
  volume pelanggaran harian. *(Sudah diimplementasikan — lihat §7.1.)*
- Job ini melakukan, dalam satu alur: promosi hot→warm (compress), warm→archive
  (kemas+pindah), lalu hapus yang lewat batas akhir (DB row + file/arsip
  sekaligus). *(Promosi warm/archive masih P1.)*

### 7.4 Pemantauan kapasitas disk
- Cek persentase disk terpakai secara berkala (mis. tiap beberapa menit,
  murah/cheap check `shutil.disk_usage`).
- Saat melewati ambang (mis. 80%): tampilkan peringatan di dashboard.
- Saat melewati ambang kritis (mis. 90–95%): kirim notifikasi (email/webhook)
  dan aktifkan mode aman — hentikan penulisan snapshot baru dengan graceful
  degradation (log pelanggaran tetap dicatat di DB tanpa foto, atau turunkan
  otomatis retensi hot) — jangan sampai proses kamera/inference crash karena
  disk penuh. *(Masih P1 — belum diimplementasikan.)*

### 7.5 VACUUM berkala
SQLite tidak mengecilkan file `.db` secara otomatis setelah `DELETE` (ruang
ditandai bebas untuk dipakai ulang, bukan dikembalikan ke OS). Jadwalkan
`VACUUM` mingguan/bulanan di luar jam sibuk supaya ukuran file `.db` di disk
benar-benar merefleksikan data yang masih ada. *(Masih P1.)*

### 7.6 Retensi vs backup — dua hal terpisah
Kebijakan retensi (§7.2) mengelola *storage pelanggan sehari-hari*. Backup
(§3, D4) adalah *jaring pengaman terpisah* — backup harus tetap menyimpan
salinan data sebelum dihapus/diarsipkan sesuai jadwalnya sendiri, supaya
kesalahan konfigurasi retensi tidak berarti kehilangan bukti yang mungkin
masih dibutuhkan investigasi. **Status: backup harian otomatis untuk
`logging.db` sudah diimplementasikan** (`_backup_worker` di `app_web.py`,
snapshot ke folder `backups/` via SQLite backup API, retensi backup
terpisah lewat `BACKUP_RETENTION_DAYS`).

### 7.7 Opsional (masa depan, tidak perlu sekarang)
Abstraksi storage backend (interface kecil `save()/list()/delete()` yang saat
ini diimplementasikan sebagai local filesystem) — supaya kalau suatu saat ada
pelanggan yang minta simpan ke NAS-mount atau object storage (MinIO/S3), itu
tinggal implementasi baru dari interface yang sama, tanpa mengubah logic
kamera/inference.

---

## 8. Dua Profil Deployment: Demo/Preview Publik vs Instance Pelanggan

Ini bukan cuma soal marketing — dari sisi teknik, ini dua *threat model* dan
kebutuhan operasional yang berbeda. Codebase yang sama (`app_web.py` +
`frontend/`) sebaiknya dipakai untuk keduanya, dibedakan lewat mode/konfigurasi
(env var), **bukan fork terpisah** — supaya tidak ada dua codebase yang harus
dirawat paralel.

### 8.1 Profil A — Instance Pelanggan (appliance on-prem)
Ini yang sudah dibahas di seluruh dokumen sebelumnya (§1–§7): 1 instance per
pelanggan, di jaringan pelanggan, data & kamera nyata, akses terbatas ke staf
pelanggan yang sudah dipercaya.

### 8.2 Profil B — Demo/Preview Publik (baru)
Tujuan: calon pelanggan bisa mengakses langsung lewat browser (link publik)
dan mencoba dashboard tanpa install apa pun. Keputusan desain yang sudah
dikonfirmasi bersama:

- **Sandbox interaktif terbatas** — pengunjung otomatis masuk sebagai akun
  "guest" (tanpa perlu daftar/login manual), bisa melihat live detection
  berjalan di beberapa **video demo preset** (bukan RTSP kamera asli), bisa
  membuka halaman Logs/Stats/Settings untuk merasakan UI — tapi **tidak bisa
  menambah kamera baru dengan URL bebas**.
- **Hosting**: VPS cloud terpisah total dari instance pelanggan manapun —
  tidak ada jalur jaringan yang menghubungkan demo ke appliance pelanggan
  mana pun.
- **Reset otomatis berkala** (mis. tiap 1–6 jam) mengembalikan data demo
  (logs, settings) ke kondisi awal yang sudah disiapkan.

#### Kenapa "tidak bisa tambah kamera bebas" itu wajib, bukan sekadar pilihan
Fitur "Add Camera" menerima URL (RTSP/HTTP/webcam index) yang lalu dipakai
server untuk membuka koneksi (`cv2.VideoCapture`, lihat `_resolve_url` di
`app_web.py`). Kalau input ini dibuka ke publik tanpa batasan di server yang
bisa diakses internet, itu jadi **SSRF-as-a-service** gratis: siapa pun bisa
menyuruh server demo membuka koneksi ke endpoint metadata cloud (mis.
`169.254.169.254`), IP privat lain di VPC yang sama, atau menjadikan server
demo sebagai proxy scanning jaringan pihak lain. Ini risiko yang tidak relevan
di Profil A (appliance di jaringan pelanggan, hanya staf terpercaya yang bisa
login) tapi kritis di Profil B (publik, anonim, siapa saja bisa mencoba). Kalau
suatu saat ingin bereksperimen dengan "demo penuh termasuk tambah kamera
sendiri", itu wajib didahului allow-list/deny-list rentang IP privat +
validasi skema URL yang ketat di sisi server — bukan hanya validasi di UI.

#### Kebutuhan teknis tambahan khusus Profil B
| # | Kebutuhan | Alasan | Status |
|---|-----------|--------|--------|
| B1 | Flag `DEMO_MODE=1` (env var) yang: (a) auto-login semua visitor sebagai akun guest read-mostly, (b) menonaktifkan endpoint pengubah state berisiko (`POST/PUT/DELETE /api/cameras`, `/api/videos/upload`, `/api/settings`, `/api/auth/change-password`), (c) memblokir kamera manapun yang bukan file video lokal (cegah SSRF) | Satu codebase, dua mode — tidak perlu fork terpisah untuk dirawat | **Sudah diimplementasikan** |
| B2 | Job reset terjadwal (cron/APScheduler) yang mengembalikan `logging.db` demo ke snapshot awal + membuang perubahan settings dari sesi pengunjung sebelumnya | Sesuai keputusan reset berkala di atas | P1 |
| B3 | Rate limiting per-IP yang jauh lebih ketat dibanding Profil A (mis. batas request/menit per IP, batas percobaan login jika ada login sungguhan) | Target pengunjung Profil B adalah publik anonim dari internet, bukan staf terpercaya seperti Profil A | **Sudah diimplementasikan** (60/menit global saat `DEMO_MODE`, 10/menit khusus login di kedua profil) |
| B4 | Anggaran GPU/compute terpisah & dibatasi (mis. instance demo pakai GPU kecil atau CPU-only, resolusi/FPS demo diturunkan) — **tidak memakai kapasitas yang sama dengan yang dijanjikan ke pelanggan** di §5.4 | Demo publik tidak boleh jadi vektor biaya cloud yang membengkak tak terduga akibat traffic pengunjung | P2 |
| B5 | Video/data demo preset harus materi yang memang disiapkan untuk didemokan, bukan cuplikan dari lokasi pelanggan asli manapun | Menghindari kebocoran data/privasi pelanggan lewat materi demo publik | P1 (operasional, bukan kode) |
| B6 | Alur yang jelas dari halaman demo menuju kontak sales/pembelian (di luar scope teknis dokumen ini, tapi perlu dicatat supaya tidak terlewat saat implementasi) | Demo tanpa jalur konversi ke penjualan kehilangan tujuan bisnisnya | P2 |
| B7 | Monitoring/alerting Profil B dipantau terpisah dari Profil A (lihat I6) | Demo publik yang down berjam-jam tanpa diketahui merusak citra di depan calon pelanggan | P1 |

#### Yang tetap dipakai bersama dari audit Profil A
Perbaikan P0 infrastruktur (WSGI production server, TLS, security headers,
rate limiting dasar) berlaku untuk **kedua profil** — demo publik justru butuh
ini lebih dulu karena langsung terekspos ke internet sejak hari pertama,
sementara appliance pelanggan (Profil A) biasanya baru terekspos ke jaringan
lokal pelanggan.

---

## 9. Roadmap Bertahap

### P0 — wajib sebelum pilot berbayar pertama
- [x] Ganti Werkzeug dev server dengan WSGI production server (waitress) (S1)
- [x] Tambahkan reverse proxy TLS-terminating (nginx, self-signed untuk
      testing) di depan backend & frontend (S2, I4)
- [x] Perbaiki `docker-compose.prod.yml` — hapus dependensi `networks.web:
      external: true` yang tidak terdokumentasi (I1)
- [x] Paksa ganti password default di login pertama, hentikan print password
      default ke log (S4)
- [x] **Perbaiki bug foto yatim** — hapus file JPEG bersamaan row DB saat
      retensi jalan (§7.1)
- [x] Backup otomatis harian untuk `logging.db` (D4)
- [x] Mask/hindari mengembalikan kredensial kamera mentah di `GET
      /api/cameras` ke UI (S6)
- [x] Bersihkan `logging.db` lama dari git history sebelum repo jadi basis
      distribusi produk (S3)
- [x] **Demo publik (Profil B)**: implementasikan `DEMO_MODE` minimal (B1) +
      rate limiting ketat per-IP (B3) SEBELUM link demo dipublikasikan ke
      siapa pun — endpoint tambah kamera/upload video wajib nonaktif di mode
      ini sejak awal, bukan menyusul

### P1 — wajib sebelum dijual umum
- [ ] Rate limiting + lockout pada login & change-password (S5) — rate limit
      dasar sudah aktif (10/menit login), lockout progresif belum
- [ ] Audit log perubahan kamera/setting/password (S11)
- [ ] Security headers di nginx (S12)
- [x] `MAX_CONTENT_LENGTH` upload video (S9) — validasi magic-bytes belum
- [ ] Session timeout eksplisit + kontrol idle-logout (S10)
- [ ] Retensi 3 tingkat (hot/warm/archive) — retensi berbasis waktu 1-tingkat
      sudah aktif (§7.2–§7.5), promosi warm/archive + alert kapasitas disk +
      VACUUM terjadwal masih belum
- [ ] Monitoring/alerting dasar: kamera offline lama, disk penuh, proses crash
      (I6)
- [ ] Capacity test terdokumentasi (§5.4) sebagai dasar klaim kapasitas resmi
      ke pelanggan
- [ ] CI dasar: build check + lint (I7)
- [ ] **Demo publik (Profil B)**: job reset otomatis berkala (B2), video/data
      demo preset yang bukan cuplikan pelanggan asli (B5), monitoring uptime
      demo terpisah (B7)

### P2 — peningkatan/skala (sesuai pertumbuhan)
- [ ] Evaluasi migrasi ke PostgreSQL (hanya jika data capacity test
      menunjukkan SQLite jadi bottleneck nyata) (D5)
- [ ] RBAC multi-user staff (bukan cuma 1 akun admin)
- [ ] Dependency vulnerability scanning otomatis (pip-audit/npm audit) (S13)
- [ ] Abstraksi storage backend untuk opsi NAS/object storage (§7.7)
- [ ] Index & FK referensial database (D1, D2), migration tooling (D3)
- [ ] Installer non-teknis, white-labeling (§6)
- [ ] **Demo publik (Profil B)**: anggaran GPU/compute terpisah & dibatasi
      (B4) jika demo mulai menarik traffic signifikan, alur konversi demo →
      sales (B6)

---

## 10. Langkah Selanjutnya
Sebagian besar item P0 sudah diimplementasikan (lihat checklist §9). Yang
masih perlu dilakukan manual sebelum go-live:
1. Jalankan `bash scripts/generate-self-signed-cert.sh` lalu `docker compose
   -f docker-compose.prod.yml up -d --build` dan lakukan satu kali full
   end-to-end test (belum dijalankan penuh di sesi ini karena image CUDA +
   PyTorch berukuran besar dan `best.pt` tidak tersedia di lingkungan audit).
2. Ganti sertifikat self-signed di `proxy/certs/` dengan sertifikat asli
   sebelum deployment produksi/demo publik.
3. Review & konfirmasi prioritas P1/P2 yang tersisa sesuai kebutuhan bisnis.
