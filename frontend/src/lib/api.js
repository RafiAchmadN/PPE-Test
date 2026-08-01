// Klien API untuk backend Flask (service terpisah — lihat ../../../app_web.py).
// Semua request memakai credentials:'include' supaya cookie sesi Flask ikut
// terkirim lintas origin (backend mengizinkannya lewat flask-cors + SameSite=Lax).

export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

async function request(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    credentials: 'include',
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
  });

  if (res.status === 401 && path !== '/api/auth/status') {
    if (unauthorizedHandler) unauthorizedHandler();
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    const err = new Error(data?.error || `Request gagal (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

const get = (path) => request(path);
const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) });
const put = (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) });
const del = (path) => request(path, { method: 'DELETE' });

// ─── Auth ──────────────────────────────────────────────────────────────────
export const login = (username, password) => post('/api/auth/login', { username, password });
export const logout = () => post('/api/auth/logout', {});
export const authStatus = () => get('/api/auth/status');
export const changePassword = (current, newPw) =>
  post('/api/auth/change-password', { current, new: newPw });

// ─── Info ──────────────────────────────────────────────────────────────────
export const getInfo = () => get('/api/info');

// ─── Cameras ───────────────────────────────────────────────────────────────
// getCameras() menyamarkan kredensial di URL — dipakai untuk tampilan list.
// getCamera(id) mengembalikan URL lengkap (termasuk kredensial) — dipakai
// saat membuka form edit supaya nilai lama tidak tertimpa string tersamar.
export const getCameras = () => get('/api/cameras');
export const getCamera = (id) => get(`/api/cameras/${id}`);
export const createCamera = (cam) => post('/api/cameras', cam);
export const updateCamera = (id, cam) => put(`/api/cameras/${id}`, cam);
export const deleteCamera = (id) => del(`/api/cameras/${id}`);
export const setVisibleCameras = (ids) => post('/api/cameras/visible', { ids });
export const streamUrl = (id) => `${API_BASE}/api/stream/${id}`;

// ─── Videos (upload untuk testing) ──────────────────────────────────────────
export const listVideos = () => get('/api/videos');
export const deleteVideo = (filename) => del(`/api/videos/${encodeURIComponent(filename)}`);
export function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append('file', file);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', API_BASE + '/api/videos/upload');
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status === 201) resolve(data);
        else reject(new Error(data?.error || 'Upload gagal'));
      } catch {
        reject(new Error('Upload gagal'));
      }
    };
    xhr.onerror = () => reject(new Error('Error jaringan saat upload'));
    xhr.send(form);
  });
}

// ─── Logs & Stats ────────────────────────────────────────────────────────────
export const getLogs = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return get(`/api/logs${qs ? '?' + qs : ''}`);
};
export const getStats = () => get('/api/stats');
export const evidenceUrl = (filename) => `${API_BASE}/foto/${filename}`;

// ─── Settings ────────────────────────────────────────────────────────────────
export const getSettings = () => get('/api/settings');
export const updateSettings = (s) => put('/api/settings', s);
