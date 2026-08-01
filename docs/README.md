# PPE Kubernetes Deployment — Konteks untuk Claude Code

## Status home lab saat ini
- Cluster: k3d `homelab` (1 server + 1 agent), berjalan via Docker Desktop di WSL2 Ubuntu
- Ingress controller: Traefik (bawaan k3d), port 8080 di host → port 80 di cluster
- Storage class default: `local-path`
- Semua health check sudah lulus (nodes Ready, coredns/traefik/metrics-server Running, DNS resolve OK)
- Sudah ada contoh deployment nginx + ingress yang berhasil diakses via `localhost:8080`

## File di folder ini
- `ppe-pv.yaml` — PersistentVolume + PVC untuk mount model YOLOv11m weights (.pt) dari WSL ke pod
- `ppe-deployment.yaml` — Deployment + Service untuk Flask app PPE
- `ppe-ingress.yaml` — Ingress rule untuk expose PPE di path `/ppe`

## Yang PERLU disesuaikan (masih placeholder / TODO)
1. **Path model di `ppe-pv.yaml`** — ganti `/mnt/d/models/ppe` dengan lokasi asli file `.pt` di WSL
2. **Port Flask** di `ppe-deployment.yaml` — cek `EXPOSE` di Dockerfile, sesuaikan `containerPort` dan `targetPort`
3. **Mount path model** di `ppe-deployment.yaml` — cek kode Flask, cari variabel seperti `MODEL_PATH` untuk tahu path yang diharapkan

## Langkah menjalankan (urutan)
```bash
# 1. Masuk ke folder project PPE (WSL)
cd "/mnt/d/Workspace Code/Codex/Python/PPE"

# 2. Build image Docker
docker build -t ppe-app:latest .

# 3. Import image ke cluster k3d (WAJIB, image lokal tidak otomatis terlihat oleh k3d)
k3d image import ppe-app:latest -c homelab

# 4. Apply manifest (sesuaikan TODO dulu sebelum ini)
kubectl apply -f ppe-pv.yaml
kubectl apply -f ppe-deployment.yaml
kubectl apply -f ppe-ingress.yaml

# 5. Cek status
kubectl get pods
kubectl logs -f deployment/ppe-deployment

# 6. Test akses
curl localhost:8080/ppe
```

## Catatan untuk Claude Code
Tolong baca `Dockerfile` dan kode Flask di project ini untuk menentukan nilai TODO di atas
(port aplikasi, path model yang di-load), lalu update ketiga file YAML sebelum di-apply.
