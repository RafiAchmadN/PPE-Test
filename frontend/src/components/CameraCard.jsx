import { streamUrl } from '../lib/api';

export default function CameraCard({ cam, fullscreen, onToggleFullscreen }) {
  return (
    <div
      className={`card bg-base-100 border border-base-300 shadow-sm overflow-hidden flex flex-col ${
        fullscreen ? 'fixed inset-0 lg:left-[72px] z-50 rounded-none' : ''
      }`}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-base-300 flex-shrink-0">
        <div className="text-sm font-semibold flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${cam.online ? 'bg-success' : 'bg-error'}`}></span>
          {cam.name}
        </div>
        <button type="button" className="btn btn-square btn-xs btn-ghost" onClick={onToggleFullscreen} title="Fullscreen">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
            <polyline points="15 3 21 3 21 9" />
            <polyline points="9 21 3 21 3 15" />
            <line x1="21" y1="3" x2="14" y2="10" />
            <line x1="3" y1="21" x2="10" y2="14" />
          </svg>
        </button>
      </div>
      <div className="aspect-video bg-black flex items-center justify-center overflow-hidden">
        {cam.online ? (
          <img src={streamUrl(cam.id)} alt={cam.name} className="w-full h-full object-contain" />
        ) : (
          <div className="flex flex-col items-center gap-2 text-base-content/40 text-sm">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-9 h-9 opacity-60">
              <circle cx="12" cy="12" r="10" />
              <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
            </svg>
            {cam.error || 'No Signal'}
          </div>
        )}
      </div>
      <div className="px-4 py-2 text-[11px] text-base-content/40 font-mono-app flex-shrink-0">FPS: {cam.fps || 0}</div>
    </div>
  );
}
