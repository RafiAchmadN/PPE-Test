import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  // nginx-gateway menyajikan dashboard ini di project.insamo.id/ppe/ (subpath,
  // bukan root/subdomain) — tanpa base ini, asset di-build dengan path absolut
  // "/assets/..." yang di-resolve browser ke root domain, bukan "/ppe/assets/...".
  // Cuma dipakai saat `npm run build` (Docker) — dev server lokal tetap di root
  // supaya http://localhost:5173 langsung jalan tanpa embel-embel /ppe/.
  // Override lewat env kalau suatu saat di-deploy di root/subpath lain:
  // VITE_BASE=/ npm run build
  base: process.env.VITE_BASE || (command === 'build' ? '/ppe/' : '/'),
  server: {
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
  },
}))
