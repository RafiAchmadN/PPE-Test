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
4. Dicoba lepas k3d sepenuhnya, pasang `k3s` langsung di WSL2 (bukan di dalam
   Docker) supaya node = WSL2 Ubuntu asli, bukan image node minimal — tapi
   kubelet gagal start sama sekali (`ContainerManager` crash-loop, error
   "system validation failed - wrong number of fields (expected 6, got 7)").
   Root cause: kubelet mem-parsing `/proc/self/mountinfo` untuk validasi
   cgroup, dan kernel WSL2 (kustom Microsoft, mount `drvfs`/9p untuk akses
   `/mnt/c` dkk) menghasilkan baris mount dengan jumlah field yang tidak
   lazim. Bukan soal swap (sudah dicoba dimatikan via `.wslconfig`, tidak
   berubah) dan bukan regresi versi terbaru (identik di `v1.36.2+k3s1` dan
   `v1.30.14+k3s2`, 6 versi minor lebih lama, 7+ kali percobaan restart) —
   ini ketidakcocokan `/proc/self/mountinfo` WSL2 vs kubelet yang berlaku di
   rentang versi luas, bukan bug spesifik satu rilis.

Kesimpulan: bukan salah konfigurasi yang bisa ditambal cepat di titik manapun
— tiga jalur berbeda (k3d image, GPU Operator, k3s bare-metal) masing-masing
mentok di ketidakcocokan WSL2 yang berbeda-beda. GPU tetap terpakai penuh di
jalur **Docker Compose** (`PPE-docker-compose.yml`) yang sudah terbukti jalan
(WSL2 + `docker run --gpus all` langsung TERBUKTI bekerja normal — masalahnya
selalu muncul begitu ada lapisan Kubernetes/kubelet/containerd tambahan di
atasnya). Jalur K8s ini murni untuk belajar konsep Kubernetes/homelab, bukan
untuk demo performa inferensi — jangan coba GPU lagi di WSL2 kecuali pindah
ke VM Linux asli (non-WSL2) atau server Linux fisik.

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

## Platform/infra terpisah dari repo ini
Config yang sifatnya cluster-wide (bukan spesifik PPE) — Helm values untuk
Prometheus/Grafana, Gitea, ArgoCD, dan Application manifest ArgoCD — hidup di
repo terpisah: `homelab-infra` (lokal di `D:\Workspace Code\Codex\homelab-infra`,
di-mirror ke Gitea sebagai `homelab-infra`). Alasan dipisah dari repo PPE:
cluster ini dipakai lintas proyek (bukan cuma PPE), jadi config platform-nya
tidak boleh terikat ke satu app tertentu. Manifest yang memang spesifik ke
cara PPE di-deploy (`ppe-pv.yaml`, `ppe-deployment.yaml`, `ppe-ingress.yaml`
di folder ini) tetap di repo PPE karena berubah bareng kode aplikasinya.

## Observability — Prometheus + Grafana (kube-prometheus-stack)
- Namespace: `monitoring`, terpisah dari `default` tempat PPE app jalan.
- Values Helm ada di `homelab-infra/helm-values/prometheus-values.yaml` —
  di-tuning untuk homelab CPU-only 2-node ini (bukan default chart yang
  berasumsi resource besar):
  - `kubeControllerManager`/`kubeScheduler`/`kubeProxy`/`kubeEtcd` dimatikan
    karena k3s menjalankan semuanya di satu proses `k3s server`, bukan
    Service terpisah yang bisa di-scrape chart — kalau dibiarkan aktif,
    target-nya permanen "down" tanpa manfaat.
  - Retensi Prometheus 3 hari, storage `local-path` (4Gi Prometheus, 1Gi
    masing-masing untuk Alertmanager & Grafana) supaya data selamat dari
    restart pod, konsisten dengan pola PVC `ppe-data-pvc`.
  - Resource requests/limits di-set eksplisit dan kecil (default chart tidak
    membatasi sama sekali) karena WSL2 VM yang menjalankan Docker Desktop
    cuma ~12 CPU/7.7Gi RAM, dipakai bersama PPE app.
  - Alertmanager tetap aktif (bukan didisable) — overhead-nya kecil dan
    relevan untuk belajar stack Prometheus secara utuh.

Install (sekali):
```bash
kubectl create namespace monitoring
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update prometheus-community
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --version 88.0.1 -f ../homelab-infra/helm-values/prometheus-values.yaml
```

Akses Grafana: `http://grafana.127.0.0.1.nip.io:8080` (subdomain nip.io
terpisah dari `ppe.127.0.0.1.nip.io`, tapi lewat host port 8080 → Traefik
yang sama — routing dibedakan lewat header `Host`, tidak perlu port
tambahan). Diekspos lewat `grafana.ingress.*` bawaan chart, bukan manifest
Ingress terpisah, supaya otomatis sinkron dengan Service tiap kali upgrade.

Ambil password admin Grafana (auto-generated, user `admin`):
```bash
kubectl get secret --namespace monitoring -l app.kubernetes.io/component=admin-secret \
  -o jsonpath="{.items[0].data.admin-password}" | base64 -d; echo
```

Dashboard cluster/node (`Kubernetes / Compute Resources / Node (Pods)`,
`Node Exporter / Nodes`) sudah tersedia otomatis lewat `kube-state-metrics`
+ `node-exporter` + default dashboard chart, tanpa import manual.

## Yang belum diimplementasikan di sini (next step, bukan tebakan)
- HTTPS di Ingress (perlu `cert-manager` + kemungkinan port tambahan di k3d)
- GPU — coba lagi HANYA kalau image node k3d diganti ke base glibc yang didukung
  NVIDIA (di luar scope k3d default), bukan dengan menambal label seperti sebelumnya
- Reset otomatis data demo (kalau file ini dipakai juga untuk demo publik ala
  Profil B, bukan cuma belajar K8s) — lihat `docs/SAAS_READINESS_AUDIT.md` §8
