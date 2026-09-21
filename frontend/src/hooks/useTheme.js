import { useEffect, useState } from 'react';

const STORAGE_KEY = 'ppe-theme';
const LIGHT = 'heti';
const DARK = 'heti-dark';

function getInitialTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === LIGHT || saved === DARK) return saved;
  } catch {
    // localStorage bisa dilarang (private browsing dsb) -- fallback ke system.
  }
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  return prefersDark ? DARK : LIGHT;
}

// Mode terang/gelap -- disimpan di localStorage per browser (bukan per akun),
// diterapkan lewat atribut data-theme di <html> yang dibaca daisyUI (lihat
// dua theme "heti"/"heti-dark" di index.css).
export function useTheme() {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Gagal simpan preferensi tidak boleh bikin app error -- next load
      // cuma balik ke deteksi system preference, bukan masalah besar.
    }
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === DARK ? LIGHT : DARK));
  }

  return { theme, isDark: theme === DARK, toggleTheme };
}
