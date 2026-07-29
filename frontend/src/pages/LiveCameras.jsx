import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../lib/api';
import CameraCard from '../components/CameraCard';
import { useVisibleCameras } from '../hooks/useVisibleCameras';

// 4 kamera per halaman — sekaligus batas jumlah kamera yang benar-benar
// streaming & dideteksi YOLO bersamaan (lihat useVisibleCameras).
const CAMS_PER_PAGE = 4;

export default function LiveCameras() {
  const [cameras, setCameras] = useState(null);
  const [error, setError] = useState(false);
  const [page, setPage] = useState(0);
  const [fullscreenId, setFullscreenId] = useState(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const data = await api.getCameras();
        if (alive) {
          setCameras(data);
          setError(false);
        }
      } catch {
        if (alive) setError(true);
      }
    }
    load();
    const id = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const enabled = (cameras || []).filter((c) => c.enabled);
  const totalPages = Math.max(1, Math.ceil(enabled.length / CAMS_PER_PAGE));
  const clampedPage = Math.min(Math.max(page, 0), totalPages - 1);
  useEffect(() => {
    if (page !== clampedPage) setPage(clampedPage);
  }, [clampedPage, page]);

  const startIdx = clampedPage * CAMS_PER_PAGE;
  const pageItems = enabled.slice(startIdx, startIdx + CAMS_PER_PAGE);

  useVisibleCameras(pageItems.map((c) => c.id));

  if (error) {
    return (
      <div className="alert alert-error">
        <span>Server tidak dapat dijangkau. Periksa koneksi atau restart container.</span>
      </div>
    );
  }

  if (cameras === null) {
    return (
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg text-primary"></span>
      </div>
    );
  }

  if (!enabled.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-base-content/40 gap-4">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-16 h-16 opacity-30">
          <path d="M23 7l-7 5 7 5V7z" />
          <rect x="1" y="5" width="15" height="14" rx="2" />
        </svg>
        <p className="text-sm">No cameras configured</p>
        <Link to="/manage" className="btn btn-primary btn-sm">
          Add Camera
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-base-content/60">
          Menampilkan kamera {startIdx + 1}-{startIdx + pageItems.length} dari {enabled.length}
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn btn-ghost btn-sm" disabled={clampedPage <= 0} onClick={() => setPage((p) => p - 1)}>
            &larr; Prev
          </button>
          <span className="text-sm font-mono-app text-base-content/60 min-w-[56px] text-center">
            {clampedPage + 1} / {totalPages}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={clampedPage >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            Next &rarr;
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {pageItems.map((c) => (
          <CameraCard
            key={c.id}
            cam={c}
            fullscreen={fullscreenId === c.id}
            onToggleFullscreen={() => setFullscreenId((id) => (id === c.id ? null : c.id))}
          />
        ))}
      </div>
    </div>
  );
}
