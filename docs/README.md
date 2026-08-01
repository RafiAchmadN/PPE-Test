# PPE Kubernetes Deployment — Konteks untuk Claude Code

## Status home lab saat ini
- Cluster: k3d `homelab` (1 server + 1 agent), berjalan via Docker Desktop di WSL2 Ubuntu
- Ingress controller: Traefik (bawaan k3d), port 8080 di host → port 80 di cluster
- Storage class default: `local-path`
- GPU: **CPU-only, sengaja** — lihat "Kenapa CPU-only" di bawah sebelum mencoba
  aktifkan GPU lagi, supaya tidak mengulang troubleshooting yang sama
- Semua health check sudah lulus (nodes Ready, coredns/traefik/metrics-server Running, DNS resolve OK)
- Sudah ada contoh deployment nginx + ingress yang berhasil diakses via `localhost:8080`

## Kenapa CPU-only (bukan belum sempat dicoba)
GPU sudah dicoba diaktifkan secara serius sebelum keputusan ini diambil — bukan
dilewati begitu saja. Ringkasan troubleshooting (detail lengkap ada di riwayat
percakapan sesi ini):
1. `k3d cluster create --gpus all` berhasil meneruskan device request GPU ke
   Docker (`docker inspect ... .HostConfig.DeviceRequests` menunjukkan
   `Capabilities: [["gpu"]]`), tapi `nvidia-smi` di dalam node gagal jalan.
2. Root cause: image node k3d (`rancher/k3s`) pakai OS dasar minimal yang
   library sistemnya (`musl`) tidak kompatibel dengan binary NVIDIA (`glibc`)
   — file `nvidia-smi` berhasil disuntik ke container tapi tidak bisa dieksekusi
   sama sekali (`exit code 127` walau dipanggil lewat path lengkap).
3. Dicoba NVIDIA GPU Operator (via Helm) sebagai jalur resmi — sempat maju
   (device request GPU-mu di WSL2 terdeteksi Docker dengan benar, `nvidia-smi`
   jalan normal lewat `docker run --gpus all` langsung), tapi Node Feature
   Discovery (NFD) bawaan Operator gagal mendeteksi GPU sebagai device PCI
   NVIDIA asli (yang terlihat cuma device virtual Microsoft GPU-PV, vendor ID
   `1414`, bukan `10de`), dan setelah label PCI ditambal manual, mentok lagi di
   error "gagal membaca OS node" — akar masalah yang sama (OS node k3d bukan
   distro Linux standar) muncul lagi di lapisan berbeda.

Kesimpulan: ini bukan salah konfigurasi yang bisa ditambal cepat, tapi
ketidakcocokan struktural antara image node k3d dan asumsi tooling NVIDIA.
GPU tetap terpakai penuh di jalur **Docker Compose** (`PPE-docker-compose.yml`)
yang sudah terbukti jalan — jalur K8s ini murni untuk belajar konsep
Kubernetes/homelab, bukan untuk demo performa inferensi.

## File di folder ini
- `ppe-pv.yaml` — PersistentVolumeClaim (storage class `local-path`, dynamic provisioning)
  untuk data runtime (`logging.db`, `data/violations`, `data/videos`, `backups/`). Model
  `.pt` TIDAK pakai volume terpisah — sudah ikut ter-bake ke image lewat `COPY . .`.
- `ppe-deployment.yaml` — Deployment + Service **backend** (Flask API, CPU-only) dan
  **frontend** (React SPA di-serve nginx), dua service terpisah sesuai arsitektur
  `PPE-docker-compose.yml` saat ini.
- `ppe-ingress.yaml` — Ingress satu host (`ppe.127.0.0.1.nip.io`) dibedakan lewat path
  (`/` → frontend, `/api` + `/foto` → backend) supaya same-origin, tidak perlu CORS.

## Perbedaan dari deployment Docker Compose (`PPE-docker-compose.yml`)
| Aspek | Docker Compose (produk ke pelanggan) | K8s homelab (demo/belajar, file ini) |
|---|---|---|
| TLS | Ya, lewat `ppe-proxy` (nginx, 2 port: 8443/5443) | Belum — HTTP saja lewat Ingress Traefik |
| Frontend ↔ backend | Beda hostname (`:8443` vs `:5443`) + CORS | Satu hostname, beda path → same-origin, tanpa CORS |
| GPU | `NVIDIA_VISIBLE_DEVICES=all` (env var), aktif & jalan | Tidak dipakai (CPU fallback) — lihat "Kenapa CPU-only" |
| Storage | Bind mount (`./data:/app/data`) | PVC dinamis via StorageClass `local-path` |
| Restart policy | `restart: unless-stopped` | Deployment otomatis reconcile (bawaan K8s) |

## Langkah menjalankan (urutan)
```bash
# 1. Masuk ke folder project PPE (WSL)
cd "/mnt/d/Workspace Code/Codex/Python/PPE"

# 2. Build KEDUA image (backend & frontend beda Dockerfile/context)
docker build -t ppe-backend:latest -f PPE-Dockerfile .
docker build -t ppe-frontend:latest \
  --build-arg VITE_API_URL=http://ppe.127.0.0.1.nip.io:8080 \
  -f frontend/Dockerfile ./frontend

# 3. Import KEDUA image ke cluster k3d (WAJIB — image lokal tidak otomatis
#    terlihat oleh k3d)
k3d image import ppe-backend:latest ppe-frontend:latest -c homelab

# 4. Apply manifest (urutan penting: PVC dulu supaya Deployment bisa mount-nya)
kubectl apply -f ppe-pv.yaml
kubectl apply -f ppe-deployment.yaml
kubectl apply -f ppe-ingress.yaml

# 5. Cek status
kubectl get pods
kubectl get pvc
kubectl logs -f deployment/ppe-backend

# 6. Test akses
curl -H "Host: ppe.127.0.0.1.nip.io" http://localhost:8080/api/auth/status
```

## Akses dari browser
Buka: `http://ppe.127.0.0.1.nip.io:8080`

Login pertama kali wajib ganti password default (`admin` / lihat log
`kubectl logs deployment/ppe-backend` untuk instruksi) — sama seperti alur di
[README.md](../README.md) utama.

## Update setelah ubah kode
```bash
docker build -t ppe-backend:latest -f PPE-Dockerfile .          # kalau backend berubah
docker build -t ppe-frontend:latest \
  --build-arg VITE_API_URL=http://ppe.127.0.0.1.nip.io:8080 \
  -f frontend/Dockerfile ./frontend                               # kalau frontend berubah
k3d image import ppe-backend:latest ppe-frontend:latest -c homelab
kubectl rollout restart deployment/ppe-backend deployment/ppe-frontend
```
`imagePullPolicy: Never` di manifest berarti K8s tidak akan otomatis ambil image baru
kecuali di-import ulang + pod di-restart manual (`rollout restart`) — beda dengan
`docker compose up -d --build` yang otomatis recreate container.

## Yang belum diimplementasikan di sini (next step, bukan tebakan)
- HTTPS di Ingress (perlu `cert-manager` + kemungkinan port tambahan di k3d)
- GPU — coba lagi HANYA kalau image node k3d diganti ke base glibc yang didukung
  NVIDIA (di luar scope k3d default), bukan dengan menambal label seperti sebelumnya
- Reset otomatis data demo (kalau file ini dipakai juga untuk demo publik ala
  Profil B, bukan cuma belajar K8s) — lihat `docs/SAAS_READINESS_AUDIT.md` §8
