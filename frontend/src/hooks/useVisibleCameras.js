import { useEffect } from 'react';
import { setVisibleCameras } from '../lib/api';

// Memberi tahu backend kamera mana yang benar-benar tertampil di layar SEKARANG,
// supaya YOLO inference dibatasi hanya untuk kamera itu (lihat _is_camera_visible
// di app_web.py). Dengan React Router, tiap halaman unmount saat ditinggalkan,
// jadi cleanup effect di bawah otomatis melepas pembatasan tanpa perlu tracking
// gabungan lintas halaman seperti versi single-page sebelumnya.
export function useVisibleCameras(ids) {
  const key = ids && ids.length ? [...ids].sort((a, b) => a - b).join(',') : '';

  useEffect(() => {
    setVisibleCameras(ids && ids.length ? ids : null).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    return () => {
      setVisibleCameras(null).catch(() => {});
    };
  }, []);
}
