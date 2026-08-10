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

# 2. Build KEDUA image (backend & frontend beda Dockerfile/context).
#    VITE_API_URL SENGAJA dikosongkan (bukan URL absolut) -- frontend &
#    backend di k3d ini same-origin lewat path routing Ingress (lihat
#    ppe-ingress.yaml), jadi fetch relative otomatis ikut hostname apa pun
#    yang dipakai akses (127.0.0.1 ATAU Tailscale IP, tanpa rebuild ulang).
#    Isi VITE_API_URL cuma perlu kalau frontend & backend beda origin
#    (kayak Docker Compose production, lihat "Update setelah ubah kode").
docker build -t ppe-backend:latest -f PPE-Dockerfile .
docker build -t ppe-frontend:latest \
  --build-arg VITE_API_URL= \
  -f frontend/Dockerfile ./frontend

# 3. Import KEDUA image ke cluster k3d (WAJIB — image lokal tidak otomatis
#    terlihat oleh k3d)
k3d image import ppe-backend:latest ppe-frontend:latest -c homelab

# 4. Buat namespace + Secret SECRET_KEY (WAJIB sebelum apply Deployment,
#    lihat "Keamanan" di bawah — Deployment mereferensikan Secret ini lewat
#    secretKeyRef, pod gagal start kalau belum ada)
kubectl create namespace ppe
kubectl create secret generic ppe-secrets -n ppe --from-literal=SECRET_KEY="$(openssl rand -hex 32)"

# 5. Apply manifest — HANYA untuk bootstrap awal (cluster baru/kosong).
#    Setelah ArgoCD terpasang (lihat "GitOps" di bawah), jangan pakai kubectl
#    apply manual lagi untuk manifest ini — ArgoCD auto-sync akan menganggapnya
#    "drift" dan menimpanya balik ke versi git (selfHeal: true).
kubectl apply -f ppe-pv.yaml -n ppe
kubectl apply -f ppe-deployment.yaml -n ppe
kubectl apply -f ppe-ingress.yaml -n ppe
kubectl apply -f ppe-networkpolicy.yaml -n ppe

# 6. Cek status
kubectl get pods -n ppe
kubectl get pvc -n ppe
kubectl logs -f deployment/ppe-backend -n ppe

# 7. Test akses
curl -H "Host: ppe.127.0.0.1.nip.io" http://localhost:8080/api/auth/status
```

## Akses dari browser
Buka: `http://ppe.127.0.0.1.nip.io:8080`

Login pertama kali wajib ganti password default (`admin` / lihat log
`kubectl logs deployment/ppe-backend -n ppe` untuk instruksi) — sama seperti
alur di [README.md](../README.md) utama.

## Keamanan (namespace, RBAC, NetworkPolicy, Secret)
- **Namespace `ppe`** — bukan `default` lagi. Isolasi blast-radius: RBAC dan
  NetworkPolicy di bawah ini scoped ke namespace, jadi lebih rapi kalau
  cluster ini nanti dipakai proyek lain juga (lihat `homelab-infra`).
- **RBAC** — `ppe-backend-sa` dan `ppe-frontend-sa` (didefinisikan di
  `ppe-deployment.yaml`), keduanya dengan `automountServiceAccountToken:
  false` dan TANPA Role/RoleBinding apa pun. App ini tidak pernah memanggil
  K8s API, jadi least-privilege yang benar bukan "kasih izin terbatas" tapi
  cabut total token-nya — pod bahkan tidak punya volume `kube-api-access-*`
  ter-mount (cek: `kubectl get pod <pod> -n ppe -o jsonpath='{.spec.volumes[*].name}'`).
- **NetworkPolicy** (`ppe-networkpolicy.yaml`) — default-deny semua ingress
  di namespace `ppe`, lalu allow eksplisit HANYA dari pod Traefik
  (`kube-system`) ke `ppe-backend-svc:5000` dan `ppe-frontend-svc:80`. Diuji
  langsung: pod acak di namespace lain yang coba `wget` ke Service ini
  ditolak (`connection refused`), sementara traffic lewat Ingress tetap
  jalan normal. Egress TIDAK dibatasi (DNS/internet tetap jalan).
- **Secret `SECRET_KEY`** — sebelumnya opsional/auto-generate & persist di
  SQLite (`app_settings` table, lihat `app_web.py`), sekarang eksplisit
  lewat K8s Secret (`ppe-deployment.yaml` pakai `secretKeyRef`). Secret-nya
  sendiri **tidak di-commit ke git** (sama seperti kredensial repo ArgoCD) —
  dibuat manual sekali via `kubectl create secret generic ppe-secrets -n ppe
  --from-literal=SECRET_KEY="$(openssl rand -hex 32)"` SEBELUM apply
  Deployment, kalau belum ada pod gagal start (`CreateContainerConfigError`).

## Update setelah ubah kode
```bash
docker build -t ppe-backend:latest -f PPE-Dockerfile .          # kalau backend berubah
docker build -t ppe-frontend:latest \
  --build-arg VITE_API_URL= \
  -f frontend/Dockerfile ./frontend                               # kalau frontend berubah
k3d image import ppe-backend:latest ppe-frontend:latest -c homelab
kubectl rollout restart deployment/ppe-backend deployment/ppe-frontend -n ppe
```
`imagePullPolicy: Never` di manifest berarti K8s tidak akan otomatis ambil image baru
kecuali di-import ulang + pod di-restart manual (`rollout restart`) — beda dengan
`docker compose up -d --build` yang otomatis recreate container.

## GitOps — deploy otomatis via ArgoCD
Setelah bootstrap awal (langkah di atas), perubahan ke `ppe-pv.yaml` /
`ppe-deployment.yaml` / `ppe-ingress.yaml` tidak lagi lewat `kubectl apply`
manual. Alurnya:

1. Edit manifest di folder ini seperti biasa.
2. `git commit` + `git push gitea master` (remote `gitea` mengarah ke
   `http://git.127.0.0.1.nip.io:8080/admin/PPE.git`, dibuat lewat
   `git remote add gitea http://admin:<password>@git.127.0.0.1.nip.io:8080/admin/PPE.git`).
3. ArgoCD (Application `ppe`, didefinisikan di repo `homelab-infra`, lihat
   `argocd-apps/ppe.yaml` di sana) polling repo ini tiap ~3 menit, deteksi
   commit baru, `kubectl apply` otomatis — tanpa perlu masuk ke cluster sama
   sekali. Cek progress: `kubectl get application ppe -n argocd`, atau lewat
   UI `http://argocd.127.0.0.1.nip.io:8080`.

Gambaran build image tetap manual (`docker build` + `k3d image import`,
lihat "Update setelah ubah kode" di atas) — ArgoCD hanya mengurus manifest
K8s, bukan build image, karena `imagePullPolicy: Never` butuh image sudah
ada di node sebelum pod dibuat.

Kenapa image dan repo yang sama (`PPE`) menyimpan manifest K8s-nya sendiri,
sementara Helm values Prometheus/Gitea/ArgoCD dan Application manifest-nya
ada di repo lain (`homelab-infra`) — lihat bagian di bawah.

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
