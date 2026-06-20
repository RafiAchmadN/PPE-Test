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
│                   Flask Backend                          │
│  /api/stream/<id> (MJPEG, 5fps)                         │
│  /api/logs, /api/stats, /api/cameras, /api/settings     │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│                 Dashboard Web (Browser)                  │
│  Live Stream + Bounding Box Overlay                     │
│  Statistik Kepatuhan + Riwayat Pelanggaran              │
│  Manajemen Kamera (CRUD) + Settings                     │
└─────────────────────────────────────────────────────────┘
```

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

### 2. Jalankan dengan Docker (Direkomendasikan)
```bash
# Build image (pertama kali, butuh ~10-15 menit download PyTorch cu128)
docker compose -f PPE-docker-compose.yml build

# Jalankan container
docker compose -f PPE-docker-compose.yml up -d

# Cek status
docker compose -f PPE-docker-compose.yml logs -f
```

### 3. Akses Dashboard
Buka browser: `http://localhost:5000/ppe`

**Login default:**
- Username: `admin`
- Password: `admin123`

### 4. Update Setelah Pull
```bash
git pull
docker compose -f PPE-docker-compose.yml build   # tanpa --no-cache (reuse layer PyTorch)
docker compose -f PPE-docker-compose.yml up -d
```

---

## Konfigurasi

### Environment Variables (`PPE-docker-compose.yml`)
```yaml
environment:
  - APP_BASE_URL=/ppe          # Base path URL (ubah jika diakses via subpath)
  - PYTHONUNBUFFERED=1
  - NVIDIA_VISIBLE_DEVICES=all # GPU visibility
```

### Volumes
```yaml
volumes:
  - ./logging.db:/app/logging.db     # Database SQLite
  - ./foto:/app/foto                 # Foto profil (unused)
  - ./data:/app/data                 # Violations snapshots & video
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
Menu **Settings** → **Change Password** → isi password baru

---

## API Reference

Semua endpoint memerlukan autentikasi (session cookie setelah login).

### Autentikasi
```http
POST /ppe/login
Content-Type: application/json
{"username": "admin", "password": "admin123"}
```

### Kamera
```http
GET    /ppe/api/cameras              # List semua kamera
POST   /ppe/api/cameras              # Tambah kamera baru
PUT    /ppe/api/cameras/<id>         # Update kamera
DELETE /ppe/api/cameras/<id>         # Hapus kamera
GET    /ppe/api/cameras/<id>/info    # Status koneksi & FPS
```

### Streaming
```http
GET /ppe/api/stream/<camera_id>      # MJPEG stream (multipart/x-mixed-replace)
```

### Statistik & Log
```http
GET /ppe/api/stats                   # Statistik pelanggaran (total, hari ini, per tipe)
GET /ppe/api/logs?start=YYYY-MM-DD&end=YYYY-MM-DD  # Riwayat pelanggaran
```

### Settings
```http
GET  /ppe/api/settings               # Baca pengaturan saat ini
POST /ppe/api/settings               # Update pengaturan
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
├── app_web.py              # Aplikasi Flask utama
├── best.pt                 # Bobot model YOLOv11m terlatih
├── PPE-Dockerfile          # Docker image (CUDA 12.8 + PyTorch cu128)
├── PPE-docker-compose.yml  # Docker Compose configuration
├── requirements.txt        # Python dependencies
├── exportdb.py             # Utilitas ekspor database ke Excel/CSV
├── logging.db              # Database SQLite (auto-generated)
├── templates/
│   ├── index.html          # Dashboard monitoring (SPA)
│   └── login.html          # Halaman login
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
| Web Framework | Flask 3.1.3 |
| Database | SQLite (via Python sqlite3) |
| Frontend | Vanilla JS + CSS (no framework) |
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
