# MAPPER — Monitoring Automated Personal Protective Equipment Detection & Reporting

Sistem deteksi kepatuhan Alat Pelindung Diri (APD) secara real-time berbasis YOLOv11 yang terintegrasi dengan feed CCTV dan dashboard monitoring website.

---

## Daftar Isi

- [Deskripsi](#deskripsi)
- [Fitur Utama](#fitur-utama)
- [Arsitektur Sistem](#arsitektur-sistem)
- [Hasil Pelatihan Model](#hasil-pelatihan-model)
- [Requirements](#requirements)
- [Instalasi & Menjalankan](#instalasi--menjalankan)
- [Konfigurasi](#konfigurasi)
- [Panduan Penggunaan](#panduan-penggunaan)
- [API Reference](#api-reference)
- [Skema Database](#skema-database)
- [Workflow Pelatihan Model](#workflow-pelatihan-model)
- [Struktur Folder](#struktur-folder)
- [Tech Stack](#tech-stack)
- [Tim Pengembang](#tim-pengembang)

---

## Deskripsi

MAPPER adalah sistem deteksi APD otomatis yang membaca feed video CCTV secara real-time, menjalankan inferensi YOLOv11 untuk mendeteksi 5 kelas APD, dan menampilkan hasilnya pada dashboard web monitoring lengkap dengan statistik kepatuhan dan riwayat pelanggaran.

**Kelas yang dideteksi:**
| ID | Kelas | Keterangan |
|----|-------|------------|
| 0 | Person | Pekerja yang terdeteksi |
| 1 | helmet | Memakai helm keselamatan |
| 2 | no_helmet | Tidak memakai helm (pelanggaran) |
| 3 | rompi | Memakai rompi keselamatan |
| 4 | no_rompi | Tidak memakai rompi (pelanggaran) |

---

## Fitur Utama

- **Deteksi Real-time** — Inferensi YOLOv11 pada setiap frame CCTV dengan overlay bounding box
- **Person-gated Detection** — Evaluasi kepatuhan APD hanya pada area yang teridentifikasi sebagai pekerja, meminimalkan false positive
- **Multi-kamera** — Mendukung banyak kamera CCTV (RTSP, webcam, file video, YouTube)
- **Dashboard Web** — Monitoring real-time dengan statistik kepatuhan, riwayat pelanggaran, dan manajemen kamera (CRUD)
- **Auto-logging** — Pelanggaran otomatis dicatat ke SQLite dengan snapshot JPEG
- **GPU Support** — CUDA support (RTX 5060 Blackwell sm_120 via CUDA 12.8 + PyTorch cu128), auto-fallback ke CPU
- **Docker Deployment** — Single command deploy dengan Docker Compose

---

## Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────┐
│                    Sumber Video                          │
│  CCTV (RTSP) / Webcam / File Video / YouTube            │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                 CameraStream Thread                      │
│  OpenCV VideoCapture → Frame Capture → Semaphore Guard  │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│              Modul Inferensi YOLOv11                     │
│  best.pt (YOLOv11m) → Person-gated → Violation Check    │
│  Device: CUDA (RTX 5060) / CPU fallback                 │
└──────────┬────────────────────────────┬─────────────────┘
           │                            │
           ▼                            ▼
┌──────────────────┐        ┌───────────────────────────┐
│  Annotated Frame │        │   Violation Logger        │
│  JPEG (640px,    │        │   SQLite + JPEG Snapshot  │
│  quality 60)     │        │                           │
└──────────┬───────┘        └─────────────┬─────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────────────────────────────────────────┐
│           Flask Backend — JSON API (:5000)                │
│  /api/stream/<id> (MJPEG, 5fps)                         │
│  /api/logs, /api/stats, /api/cameras, /api/settings     │
│  CORS (flask-cors) + session cookie                     │
└───────────────────────┬─────────────────────────────────┘
                        │  fetch (credentials: include)
                        ▼
┌─────────────────────────────────────────────────────────┐
│     Frontend — React + Tailwind + daisyUI (:8080/:5173)  │
│  Live Stream + Bounding Box Overlay                     │
│  Statistik Kepatuhan (radial meter) + Riwayat Pelanggaran│
│  Manajemen Kamera (CRUD) + Settings                     │
└─────────────────────────────────────────────────────────┘
```

Backend dan frontend adalah dua service independen (dua container, dua port) yang
berkomunikasi lewat HTTP + CORS — bukan lagi Flask yang me-render halaman. Lihat
`frontend/` untuk source React dan `app_web.py` untuk API.

---

## Hasil Pelatihan Model

**Model:** YOLOv11m | **Dataset:** ±6.209 gambar, ±39.944 anotasi | **Epoch:** 200 (terbaik: 108)

| Metrik | Nilai |
|--------|-------|
| mAP@50 | **97,63%** |
| mAP@50–95 | 71,84% |
| Precision | 95,06% |
| Recall | 93,60% |

**Komposisi Dataset:**
| Kelas | Jumlah Anotasi |
|-------|---------------|
| Person | 12.945 |
| helmet | 10.380 |
| no_helmet | 3.396 |
| rompi | 9.462 |
| no_rompi | 3.761 |
| **Total** | **±39.944** |

**Hyperparameter Training:**
```yaml
model: YOLOv11m
epochs: 200
batch: 8
imgsz: 640
optimizer: AdamW
lr0: 0.01
amp: true          # Automatic Mixed Precision
patience: 50
augmentation: mosaic, flipLR=0.5, randaugment, erasing=0.4
```

**Kurva Metrik per Epoch:**
| Epoch | mAP@50 | Precision | Recall |
|-------|--------|-----------|--------|
| 1 | 84,07% | 83,75% | 76,85% |
| 50 | 97,24% | 94,40% | 92,29% |
| 100 | 97,41% | 94,53% | 93,57% |
| **108 (best)** | **97,63%** | **94,29%** | **94,08%** |
| 150 | 97,36% | 94,84% | 93,79% |
| 200 | 97,33% | 95,06% | 93,60% |

---

## Requirements

### Minimal
- Docker Desktop (dengan WSL2 di Windows)
- 8 GB RAM
- GPU NVIDIA (opsional, CPU fallback tersedia)

### GPU Support
| GPU | CUDA | PyTorch |
|-----|------|---------|
| RTX 5060 (Blackwell sm_120) | 12.8 | cu128 |
| RTX 3000/4000 series | 12.1+ | cu121+ |
| RTX 2060 (training) | 11.8+ | cu118+ |

---

## Instalasi & Menjalankan

### 1. Clone Repository
```bash
git clone https://github.com/RafiAchmadN/PPE-Test.git
cd PPE-Test
```

### 2. Generate Sertifikat TLS (sekali saja)
Backend, frontend, dan proxy TLS-terminating (`ppe-proxy`) adalah tiga service
terpisah — lihat [Arsitektur Sistem](#arsitektur-sistem). Proxy butuh
sertifikat sebelum container pertama kali dijalankan:

```bash
bash scripts/generate-self-signed-cert.sh
```

> Ini membuat sertifikat **self-signed** (hanya untuk testing/LAN — browser
> akan menampilkan peringatan "Not Secure"). Untuk produksi/demo publik, timpa
> `proxy/certs/cert.pem` + `key.pem` dengan sertifikat asli (Let's Encrypt/CA
> internal) — tidak perlu ubah konfigurasi lain.

### 3. Jalankan dengan Docker (Direkomendasikan)
```bash
# Build image (pertama kali, butuh ~10-15 menit download PyTorch cu128)
docker compose -f PPE-docker-compose.yml build

# Jalankan semua container (backend & frontend tidak lagi publish port host —
# satu-satunya jalan masuk dari luar adalah lewat ppe-proxy)
docker compose -f PPE-docker-compose.yml up -d

# Cek status
docker compose -f PPE-docker-compose.yml logs -f
```

### 4. Akses Dashboard
Buka browser: `https://localhost:8443` (terima peringatan sertifikat
self-signed di browser — sekali saja per browser).

**Login pertama kali wajib ganti password default** (`admin` / lihat pesan di
log startup container) — dashboard akan otomatis meminta ganti password
sebelum bisa mengakses fitur lain.

### 5. Update Setelah Pull
```bash
git pull
docker compose -f PPE-docker-compose.yml build   # tanpa --no-cache (reuse layer PyTorch)
docker compose -f PPE-docker-compose.yml up -d
```

### 6. Jalankan Manual untuk Development (tanpa Docker)
```bash
# Terminal 1 — backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DEV_SERVER=1 python app_web.py    # http://localhost:5000 (dev server Werkzeug, BUKAN untuk produksi)

# Terminal 2 — frontend
cd frontend
npm install
npm run dev                       # http://localhost:5173 (proxy ke backend via VITE_API_URL)
```
> Tanpa `DEV_SERVER=1`, `app_web.py` akan mencoba menjalankan **waitress**
> (WSGI server produksi) — install dulu lewat `pip install -r requirements.txt`.
> Untuk iterasi cepat di localhost, dev server Werkzeug (`DEV_SERVER=1`) lebih
> praktis; JANGAN pakai `DEV_SERVER=1` untuk deployment ke pelanggan.

---

## Konfigurasi

### Environment Variables

**Backend** (`PPE-docker-compose.yml` → service `ppe-backend`):
```yaml
environment:
  - FRONTEND_ORIGIN=https://localhost:8443  # Origin frontend (lewat proxy) yang diizinkan CORS
  - SESSION_COOKIE_SECURE=1                 # Aman karena proxy sudah menyediakan HTTPS
  - PYTHONUNBUFFERED=1
  - NVIDIA_VISIBLE_DEVICES=all              # GPU visibility
  # - SECRET_KEY=ganti-dengan-random-string-panjang   (opsional — default sudah auto-generate & persist di DB)
  # - DEMO_MODE=1             # HANYA di instance demo publik terpisah — lihat docs/SAAS_READINESS_AUDIT.md §8
  # - WEB_THREADS=32          # jumlah thread waitress — naikkan jika banyak viewer MJPEG bersamaan
  # - BACKUP_RETENTION_DAYS=14
  # - MAX_UPLOAD_MB=500
```

**Frontend** (`frontend/.env` atau build arg `VITE_API_URL` di `PPE-docker-compose.yml`):
```env
VITE_API_URL=https://localhost:5443   # Base URL backend (lewat proxy) yang bisa diakses browser
```
> `VITE_API_URL` di-*bake* ke bundle JS saat `npm run build` — kalau backend diakses lewat
> domain/IP lain, set env var ini sebelum build ulang frontend.

### Volumes
```yaml
volumes:
  - ./logging.db:/app/logging.db     # Database SQLite
  - ./data:/app/data                 # Violations snapshots & video upload
  - ./backups:/app/backups           # Snapshot backup harian logging.db — arahkan ke disk sekunder/NAS
```

### Pengaturan Deteksi (via Dashboard Settings)
| Parameter | Default | Keterangan |
|-----------|---------|------------|
| Confidence (PPE) | 0.50 | Threshold deteksi kelas APD |
| Person Confidence | 0.70 | Threshold deteksi kelas Person |
| Violation Delay | 1 detik | Interval minimum logging per kamera |
| Stream FPS | 5 | Frame rate MJPEG stream ke browser |
| Inference | Enabled | Toggle on/off inferensi YOLOv11 |

---

## Panduan Penggunaan

### Menambah Kamera
1. Login → menu **Cameras** → **Add Camera**
2. Isi nama kamera dan URL sumber:
   - RTSP: `rtsp://username:password@192.168.1.100:554/stream1`
   - Webcam: `0` (kamera default) atau `1`, `2`, dst.
   - File video: path file (contoh: `/app/data/videos/test.mp4`)
   - YouTube: URL YouTube langsung
3. Klik **Save** → aktifkan toggle **Enabled**

### Monitoring Pelanggaran
- Dashboard utama menampilkan live stream semua kamera aktif
- Frame rate: 5 FPS (dapat diatur di Settings)
- Bounding box:
  - **Hijau**: APD lengkap (helm + rompi)
  - **Merah**: Pelanggaran APD terdeteksi
- Menu **Logs** → filter tanggal → lihat riwayat + snapshot

### Mengubah Password Admin
Menu **Settings** → **Change Password** → isi password baru. Login pertama
kali (password masih default) akan otomatis diarahkan ke layar ganti password
sebelum bisa mengakses menu lain.

---

## API Reference

Backend (`https://localhost:5443` lewat proxy) adalah JSON API murni — semua
endpoint `/api/*` memerlukan autentikasi (session cookie, credentials
cross-origin lewat CORS).

### Autentikasi
```http
POST /api/auth/login
Content-Type: application/json
{"username": "admin", "password": "<password admin>"}

POST /api/auth/logout
GET  /api/auth/status                # {"logged_in", "must_change_password", "demo_mode"}
POST /api/auth/change-password       # {"current": "...", "new": "..."} — dinonaktifkan saat DEMO_MODE
```

### Kamera
```http
GET    /api/cameras                  # List kamera + status online/fps — URL disamarkan (kredensial disembunyikan)
GET    /api/cameras/<id>             # Detail 1 kamera dengan URL lengkap (dipakai form edit)
POST   /api/cameras                  # Tambah kamera baru — dinonaktifkan saat DEMO_MODE
PUT    /api/cameras/<id>             # Update kamera — dinonaktifkan saat DEMO_MODE
DELETE /api/cameras/<id>             # Hapus kamera — dinonaktifkan saat DEMO_MODE
POST   /api/cameras/visible          # {"ids":[1,2]} kamera yang tertampil di frontend saat ini
                                      # (membatasi YOLO inference — kirim {"ids":null} untuk lepas batas)
```

### Streaming & Upload Video
```http
GET    /api/stream/<camera_id>       # MJPEG stream (multipart/x-mixed-replace)
GET    /api/videos                   # List video yang sudah di-upload
POST   /api/videos/upload            # Upload file video untuk testing
DELETE /api/videos/<filename>        # Hapus video upload
```

### Statistik & Log
```http
GET /api/stats                       # Total/hari ini pelanggaran, kamera aktif/online,
                                      # compliance_pct & compliant/violation_frames (kepatuhan APD)
GET /api/logs?start=YYYY-MM-DD&end=YYYY-MM-DD&limit=200  # Riwayat pelanggaran
GET /foto/<filename>                 # Snapshot bukti pelanggaran (JPEG)
```

### Settings
```http
GET /api/settings                    # Baca pengaturan saat ini
PUT /api/settings                    # Update pengaturan
```

---

## Skema Database

Database SQLite (`logging.db`) memiliki 3 tabel:

### Tabel `cameras`
```sql
CREATE TABLE cameras (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,          -- Nama kamera
    url        TEXT NOT NULL,          -- URL sumber (RTSP/webcam/file)
    enabled    INTEGER DEFAULT 1,      -- 1=aktif, 0=nonaktif
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### Tabel `data` (Log Pelanggaran)
```sql
CREATE TABLE data (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    Tanggal TEXT,           -- Tanggal pelanggaran (YYYY-MM-DD)
    Waktu   TEXT,           -- Waktu pelanggaran (HH:MM:SS)
    Lokasi  TEXT,           -- Nama kamera
    Bukti   TEXT,           -- Path file snapshot JPEG
    jenis   TEXT DEFAULT '' -- Jenis pelanggaran: 'no_helmet' / 'no_rompi'
);
```

### Tabel `app_settings`
```sql
CREATE TABLE app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
-- Keys: 'secret_key', 'admin_pw_hash'
```

---

## Workflow Pelatihan Model

Script pelatihan tersedia di folder `workflow/`:

```bash
# Step 1: Ekstrak frame dari video
python workflow/step1_extract_frames.py

# Step 2: Auto-anotasi dengan model pre-trained (opsional)
python workflow/step2_auto_annotate.py

# Step 2b: Remap label jika diperlukan
python workflow/step2b_remap_labels.py

# Step 3: Split dataset (train/val/test)
python workflow/step3_split_dataset.py

# Step 4: Latih YOLOv11
python workflow/step4_train.py
```

**Konfigurasi training (step4_train.py):**
- Model: `yolo11m.pt` (pretrained)
- Epochs: 200, Batch: 8, imgsz: 640
- Optimizer: AdamW, AMP: True
- Output: `ppe_train/round_1/weights/best.pt`

---

## Struktur Folder

```
PPE-Test/
├── app_web.py              # Backend Flask — JSON API murni (CORS + session)
├── best.pt                 # Bobot model YOLOv11m terlatih
├── PPE-Dockerfile          # Docker image backend (CUDA 12.8 + PyTorch cu128)
├── PPE-docker-compose.yml  # Docker Compose — service ppe-backend + ppe-frontend + ppe-proxy
├── requirements.txt        # Python dependencies
├── exportdb.py             # Utilitas ekspor database ke Excel/CSV
├── logging.db              # Database SQLite (auto-generated)
├── backups/                # Snapshot backup harian logging.db (auto-generated)
├── static/                 # Aset dilayani langsung Flask (logo HETI, dll)
├── proxy/                  # Reverse proxy TLS-terminating (nginx) — satu-satunya entrypoint publik
│   ├── Dockerfile
│   ├── nginx.conf
│   └── certs/               # cert.pem + key.pem (generate via scripts/, tidak di-commit)
├── scripts/
│   └── generate-self-signed-cert.sh   # Bikin sertifikat TLS untuk testing/LAN
├── docs/
│   └── SAAS_READINESS_AUDIT.md        # Audit kesiapan komersialisasi + roadmap
├── frontend/                # Frontend React + Tailwind + daisyUI (service terpisah)
│   ├── Dockerfile           # Multi-stage build → nginx
│   ├── nginx.conf           # SPA fallback routing
│   ├── package.json
│   ├── .env.development     # VITE_API_URL untuk dev lokal
│   └── src/
│       ├── App.jsx          # Routing (react-router-dom)
│       ├── lib/api.js       # Klien fetch ke backend
│       ├── context/         # AuthContext (status login + must_change_password)
│       ├── hooks/           # useVisibleCameras (sinkron kamera aktif ↔ YOLO)
│       ├── components/      # Sidebar, Topbar, StatCard, ComplianceMeter, dll
│       └── pages/           # Dashboard, LiveCameras, CameraManagement, Logs, Settings, ForcePasswordChange
├── data/
│   ├── violations/         # Snapshot JPEG pelanggaran
│   └── videos/             # File video untuk testing
├── workflow/               # Script pelatihan model
│   ├── step1_extract_frames.py
│   ├── step2_auto_annotate.py
│   ├── step2b_remap_labels.py
│   ├── step3_split_dataset.py
│   └── step4_train.py
└── ppe_train/
    └── round_1/            # Hasil training
        ├── weights/
        │   └── best.pt     # Bobot terbaik (epoch 108)
        ├── results.csv     # Metrik per epoch
        ├── results.png     # Kurva training
        ├── confusion_matrix.png
        └── BoxPR_curve.png
```

---

## Tech Stack

| Komponen | Teknologi |
|----------|-----------|
| Object Detection | YOLOv11m (Ultralytics) |
| Video Processing | OpenCV 4.13 |
| Backend API | Flask 3.1.3 + flask-cors (JSON API murni) |
| Database | SQLite (via Python sqlite3) |
| Frontend | React 19 + React Router + Tailwind CSS v4 + daisyUI v5 (service terpisah) |
| Frontend Build/Serve | Vite (dev) → nginx (production, static build) |
| Container | Docker + NVIDIA Container Toolkit |
| GPU | CUDA 12.8 + PyTorch cu128 |
| Python | 3.11 |
| Base Image | nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04 |

---

## Tim Pengembang

**Project Based Learning — Semester Genap 2025/2026**  
Program Studi Sarjana Terapan Teknologi Rekayasa Otomasi  
Departemen Teknik Elektro Otomasi, Fakultas Vokasi  
Institut Teknologi Sepuluh Nopember (ITS) Surabaya

| Nama | NRP | Peran |
|------|-----|-------|
| Aditya Fernanda | 2040241031 | Project Manager |
| Rafi Achmad Nabihan | 2040241050 | Arsitektur sistem, backend Flask, deployment |
| Syafiq Rahman Alif | 2040241001 | Dataset, anotasi, pelatihan model |

---

## Lisensi

Proyek ini dikembangkan untuk keperluan akademik. Source code tersedia untuk referensi dan pengembangan lebih lanjut.
