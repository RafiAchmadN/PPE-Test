// Helper untuk referensi file di frontend/public/ (logo, dll) dari komponen
// React. String literal seperti src="/heti-icon.png" TIDAK ikut ditulis ulang
// Vite ke "/ppe/heti-icon.png" saat build (beda dengan referensi di
// index.html, yang memang diproses Vite) -- di production (subpath /ppe/)
// itu jadi salah alamat, browser minta ke root domain, bukan /ppe/.
// import.meta.env.BASE_URL selalu diakhiri "/" (lihat vite.config.js: "/"
// saat dev, "/ppe/" saat build), jadi cukup digabung setelah slash awal
// path-nya dibuang.
export function asset(path) {
  return import.meta.env.BASE_URL + path.replace(/^\//, '');
}
