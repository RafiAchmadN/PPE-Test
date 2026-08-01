import { useCallback, useEffect, useState } from 'react';
import * as api from '../lib/api';
import TutorialCollapse from '../components/TutorialCollapse';
import CameraFormModal from '../components/CameraFormModal';
import UploadVideoModal from '../components/UploadVideoModal';

export default function CameraManagement() {
  const [cameras, setCameras] = useState(null);
  const [error, setError] = useState(false);
  const [editing, setEditing] = useState(undefined); // undefined=closed, null=add, object=edit
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.getCameras();
      setCameras(data);
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave(payload) {
    if (editing && editing.id) {
      await api.updateCamera(editing.id, payload);
    } else {
      await api.createCamera(payload);
    }
    setEditing(undefined);
    load();
  }

  async function handleDelete(cam) {
    if (!confirm(`Delete camera "${cam.name}"?`)) return;
    await api.deleteCamera(cam.id);
    load();
  }

  async function handleEditClick(cam) {
    try {
      // List menyamarkan kredensial di URL — ambil detail lengkap dulu supaya
      // form edit tidak menimpa URL asli dengan string tersamar saat disimpan.
      const full = await api.getCamera(cam.id);
      setEditing(full);
    } catch {
      setEditing(cam);
    }
  }

  function handleUseUploadedVideo(path) {
    setUploading(false);
    setEditing({ name: 'Video Test', url: path, enabled: 1 });
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold">Camera Management</h2>
        <div className="flex gap-2">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setUploading(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="16 16 12 12 8 16" />
              <line x1="12" y1="12" x2="12" y2="21" />
              <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3" />
            </svg>
            Upload Video
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => setEditing(null)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add Camera
          </button>
        </div>
      </div>

      <TutorialCollapse />

      <div className="card bg-base-100 border border-base-300 shadow-sm overflow-hidden">
        {error ? (
          <div className="p-10 text-center text-error text-sm">Gagal memuat data kamera.</div>
        ) : cameras === null ? (
          <div className="p-10 flex justify-center">
            <span className="loading loading-spinner loading-md text-primary"></span>
          </div>
        ) : !cameras.length ? (
          <div className="p-10 text-center text-base-content/40 text-sm">Belum ada kamera. Klik "Add Camera".</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Name</th>
                  <th>URL / Source</th>
                  <th>Status</th>
                  <th>FPS</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {cameras.map((c, i) => (
                  <tr key={c.id} className="hover">
                    <td className="text-base-content/40">{i + 1}</td>
                    <td className="font-semibold">{c.name}</td>
                    <td>
                      <span className="font-mono-app text-xs text-base-content/60 block max-w-[340px] truncate" title={c.url}>
                        {c.url}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`badge badge-sm ${
                          c.enabled ? (c.online ? 'badge-success badge-soft' : 'badge-error badge-soft') : 'badge-ghost'
                        }`}
                      >
                        {c.enabled ? (c.online ? 'Online' : 'Offline') : 'Disabled'}
                      </span>
                    </td>
                    <td className="font-mono-app text-xs">{c.fps || 0}</td>
                    <td>
                      <div className="flex gap-1.5">
                        <button type="button" className="btn btn-ghost btn-xs" onClick={() => handleEditClick(c)}>
                          Edit
                        </button>
                        <button type="button" className="btn btn-error btn-soft btn-xs" onClick={() => handleDelete(c)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing !== undefined && <CameraFormModal camera={editing} onClose={() => setEditing(undefined)} onSave={handleSave} />}
      {uploading && <UploadVideoModal onClose={() => setUploading(false)} onUseAsCamera={handleUseUploadedVideo} />}
    </div>
  );
}
