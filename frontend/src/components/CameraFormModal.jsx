import { useState } from 'react';

const RTSP_TEMPLATES = {
  hikvision: 'rtsp://admin:password@{IP}:554/Streaming/Channels/101',
  dahua: 'rtsp://admin:password@{IP}:554/cam/realmonitor?channel=1&subtype=0',
  generic: 'rtsp://admin:password@{IP}:554/stream',
};

export default function CameraFormModal({ camera, onClose, onSave }) {
  const isEdit = !!camera?.id;
  const [name, setName] = useState(camera?.name || '');
  const [ip, setIp] = useState('');
  const [url, setUrl] = useState(camera?.url || '');
  const [enabled, setEnabled] = useState(camera ? (camera.enabled ? '1' : '0') : '1');
  const [saving, setSaving] = useState(false);

  function fillRtsp(brand) {
    const useIp = ip.trim() || '192.168.1.x';
    if (!ip.trim()) setIp(useIp);
    setUrl(RTSP_TEMPLATES[brand].replace('{IP}', useIp));
  }

  function onIpInput(value) {
    const prevIp = ip;
    setIp(value);
    if (!value.trim()) return;
    setUrl((cur) => {
      const matchedTpl = Object.values(RTSP_TEMPLATES).find((t) => cur === t.replace('{IP}', prevIp));
      const tpl = matchedTpl || RTSP_TEMPLATES.generic;
      return tpl.replace('{IP}', value.trim());
    });
  }

  async function handleSave() {
    setSaving(true);
    try {
      await onSave({ name, url, enabled: parseInt(enabled, 10) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal modal-open">
      <div className="modal-box">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-semibold text-base">{isEdit ? 'Edit Camera' : 'Tambah Kamera'}</h3>
          <button type="button" className="btn btn-sm btn-circle btn-ghost" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Camera Name</label>
            <input
              className="input input-bordered w-full"
              placeholder="e.g. Lobby Entrance"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">
              IP Kamera (opsional — auto-isi URL RTSP)
            </label>
            <input
              className="input input-bordered w-full"
              placeholder="192.168.1.x"
              value={ip}
              onChange={(e) => onIpInput(e.target.value)}
            />
            <div className="text-[11px] text-base-content/40 mt-1">
              Masukkan IP untuk auto-isi URL, atau isi URL manual di bawah
            </div>
          </div>
          <div>
            <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Stream URL / Source</label>
            <input
              className="input input-bordered w-full mb-1.5"
              placeholder="rtsp://user:pass@192.168.1.x:554/stream"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <div className="text-[11px] text-base-content/40 mb-2.5">
              RTSP, HTTP MJPEG, file video, atau angka (0 = webcam lokal)
            </div>
            <div className="flex gap-1.5 flex-wrap mb-2.5">
              <button type="button" className="btn btn-ghost btn-xs" onClick={() => fillRtsp('hikvision')}>
                Hikvision
              </button>
              <button type="button" className="btn btn-ghost btn-xs" onClick={() => fillRtsp('dahua')}>
                Dahua
              </button>
              <button type="button" className="btn btn-ghost btn-xs" onClick={() => fillRtsp('generic')}>
                Generic
              </button>
            </div>
            <div className="bg-base-200 border border-base-300 rounded-lg p-3 text-[11px] text-base-content/60 leading-loose">
              <div className="font-semibold text-base-content/40 uppercase tracking-wide text-[10px] mb-1">Contoh URL</div>
              <div>
                <span className="text-base-content/40 inline-block w-[90px]">Hikvision</span>
                <span className="font-mono-app text-primary">rtsp://admin:pass@192.168.1.x:554/Streaming/Channels/101</span>
              </div>
              <div>
                <span className="text-base-content/40 inline-block w-[90px]">Dahua</span>
                <span className="font-mono-app text-primary">
                  rtsp://admin:pass@192.168.1.x:554/cam/realmonitor?channel=1&subtype=0
                </span>
              </div>
              <div>
                <span className="text-base-content/40 inline-block w-[90px]">DVR Xiongmai</span>
                <span className="font-mono-app text-primary">dvrip://admin:pass@192.168.1.x:34567/0</span>
              </div>
              <div>
                <span className="text-base-content/40 inline-block w-[90px]">Webcam lokal</span>
                <span className="font-mono-app text-primary">0</span>
              </div>
            </div>
          </div>
          <div>
            <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Enabled</label>
            <select className="select select-bordered w-full" value={enabled} onChange={(e) => setEnabled(e.target.value)}>
              <option value="1">Yes</option>
              <option value="0">No</option>
            </select>
          </div>
        </div>

        <div className="modal-action">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving || !name || !url}>
            {saving ? <span className="loading loading-spinner loading-sm"></span> : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
