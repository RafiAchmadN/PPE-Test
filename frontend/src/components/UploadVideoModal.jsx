import { useRef, useState } from 'react';
import { uploadVideo } from '../lib/api';

export default function UploadVideoModal({ onClose, onUseAsCamera }) {
  const [fileName, setFileName] = useState('');
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('idle'); // idle | uploading | done | error
  const [result, setResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  function handleFile(file) {
    if (!file) return;
    setFileName(file.name);
    setStatus('uploading');
    setProgress(0);
    setResult(null);
    uploadVideo(file, setProgress)
      .then((data) => {
        setResult(data);
        setStatus('done');
      })
      .catch((err) => {
        setStatus('error');
        setResult({ error: err.message });
      });
  }

  return (
    <div className="modal modal-open">
      <div className="modal-box w-[520px]">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-semibold text-base">Upload Video untuk Testing</h3>
          <button type="button" className="btn btn-sm btn-circle btn-ghost" onClick={onClose}>
            ✕
          </button>
        </div>

        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
            dragOver ? 'border-primary bg-primary/5' : 'border-base-300'
          }`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            handleFile(e.dataTransfer.files[0]);
          }}
        >
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mx-auto mb-3 text-base-content/40">
            <polyline points="16 16 12 12 8 16" />
            <line x1="12" y1="12" x2="12" y2="21" />
            <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3" />
          </svg>
          <div className="text-sm text-base-content/60 mb-1">Klik atau drag &amp; drop file video</div>
          <div className="text-[11px] text-base-content/40">Format: .mp4 .avi .mov .mkv .webm — Maks 2GB</div>
          <input
            ref={inputRef}
            type="file"
            accept=".mp4,.avi,.mov,.mkv,.webm,.m4v"
            className="hidden"
            onChange={(e) => handleFile(e.target.files[0])}
          />
        </div>

        {status === 'uploading' && (
          <div className="mt-4">
            <div className="flex justify-between mb-1.5 text-sm">
              <span className="text-base-content/60">{fileName}</span>
              <span className="font-mono-app text-primary">{progress}%</span>
            </div>
            <progress className="progress progress-primary w-full" value={progress} max="100"></progress>
          </div>
        )}

        {status === 'error' && (
          <div role="alert" className="alert alert-error alert-soft mt-4 text-sm">
            {result?.error || 'Upload gagal'}
          </div>
        )}

        {status === 'done' && result && !result.error && (
          <div className="mt-4 bg-success/10 border border-success/30 rounded-lg p-3">
            <div className="text-xs text-success mb-1.5 font-semibold">Upload berhasil! Salin path berikut sebagai URL kamera:</div>
            <div className="flex gap-2 items-center">
              <code className="text-xs text-primary bg-base-200 px-2.5 py-1.5 rounded flex-1 break-all font-mono-app">{result.path}</code>
              <button type="button" className="btn btn-ghost btn-xs" onClick={() => navigator.clipboard.writeText(result.path)}>
                Salin
              </button>
            </div>
            <button type="button" className="btn btn-primary btn-sm w-full mt-2.5" onClick={() => onUseAsCamera(result.path)}>
              + Tambah sebagai Kamera Baru
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
