import { useEffect, useState } from 'react';
import * as api from '../lib/api';

function SettingRow({ label, desc, children, last }) {
  return (
    <div className={`flex items-center justify-between py-3 ${last ? '' : 'border-b border-base-300'}`}>
      <div>
        <div className="text-sm">{label}</div>
        {desc && <div className="text-xs text-base-content/40">{desc}</div>}
      </div>
      {children}
    </div>
  );
}

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState(false);
  const [serverAddr, setServerAddr] = useState('');
  const [pwCurrent, setPwCurrent] = useState('');
  const [pwNew, setPwNew] = useState('');
  const [pwMsg, setPwMsg] = useState(null);
  const [settingsErr, setSettingsErr] = useState('');

  useEffect(() => {
    api.getSettings().then(setSettings);
    api
      .getInfo()
      .then((d) => setServerAddr(d?.access_url || ''))
      .catch(() => {});
  }, []);

  function updateField(key, value) {
    setSettings((s) => ({ ...s, [key]: value }));
  }

  async function handleSaveSettings() {
    setSettingsErr('');
    try {
      await api.updateSettings(settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setSettingsErr(err.message || 'Gagal menyimpan settings');
    }
  }

  async function handleChangePassword() {
    try {
      await api.changePassword(pwCurrent, pwNew);
      setPwMsg({ ok: true, text: 'Password berhasil diubah!' });
    } catch (err) {
      setPwMsg({ ok: false, text: err.message || 'Gagal' });
    }
    setPwCurrent('');
    setPwNew('');
    setTimeout(() => setPwMsg(null), 3000);
  }

  if (!settings) {
    return (
      <div className="flex justify-center py-16">
        <span className="loading loading-spinner loading-lg text-primary"></span>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-base font-semibold mb-5">Settings</h2>

      <div className="card bg-base-100 border border-base-300 shadow-sm p-6 mb-4">
        <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          Detection &amp; Performance
        </h3>
        <SettingRow label="Violation Delay" desc="Seconds between captures per camera (reduce server load)">
          <input
            type="number"
            min="5"
            max="600"
            step="5"
            className="input input-bordered w-[100px] text-right font-mono-app"
            value={settings.violation_delay}
            onChange={(e) => updateField('violation_delay', e.target.value)}
          />
        </SettingRow>
        <SettingRow label="Confidence Threshold" desc="Minimum detection confidence for PPE objects (0.1 – 1.0)">
          <input
            type="number"
            min="0.1"
            max="1.0"
            step="0.05"
            className="input input-bordered w-[100px] text-right font-mono-app"
            value={settings.confidence}
            onChange={(e) => updateField('confidence', e.target.value)}
          />
        </SettingRow>
        <SettingRow label="Person Confidence" desc="Person harus terdeteksi di atas threshold ini baru dianggap valid (0.5 – 1.0)">
          <input
            type="number"
            min="0.5"
            max="1.0"
            step="0.05"
            className="input input-bordered w-[100px] text-right font-mono-app"
            value={settings.person_confidence}
            onChange={(e) => updateField('person_confidence', e.target.value)}
          />
        </SettingRow>
        <SettingRow label="Stream FPS Cap" desc="Max frames per second for MJPEG streams">
          <input
            type="number"
            min="1"
            max="30"
            step="1"
            className="input input-bordered w-[100px] text-right font-mono-app"
            value={settings.stream_fps}
            onChange={(e) => updateField('stream_fps', e.target.value)}
          />
        </SettingRow>
        <SettingRow label="AI Inference" desc="Enable/disable YOLO detection on camera feeds" last>
          <input
            type="checkbox"
            className="toggle toggle-primary"
            checked={!!settings.inference_enabled}
            onChange={(e) => updateField('inference_enabled', e.target.checked)}
          />
        </SettingRow>
      </div>

      <div className="flex items-center gap-3">
        <button type="button" className="btn btn-primary" onClick={handleSaveSettings}>
          Save Settings
        </button>
        <span className={`text-success text-sm transition-opacity ${saved ? 'opacity-100' : 'opacity-0'}`}>Saved!</span>
        {settingsErr && <span className="text-error text-sm">{settingsErr}</span>}
      </div>

      <div className="card bg-base-100 border border-base-300 shadow-sm p-6 mt-5">
        <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary">
            <rect x="3" y="11" width="18" height="11" rx="2" />
            <path d="M7 11V7a5 5 0 0110 0v4" />
          </svg>
          Keamanan &amp; Akses
        </h3>
        <div className="text-xs text-base-content/60 mb-4 font-mono-app">Akses jaringan: {serverAddr}</div>
        <SettingRow label="Password Lama">
          <input
            type="password"
            className="input input-bordered w-[200px]"
            placeholder="password saat ini"
            value={pwCurrent}
            onChange={(e) => setPwCurrent(e.target.value)}
          />
        </SettingRow>
        <SettingRow label="Password Baru" desc="Minimal 6 karakter" last>
          <input
            type="password"
            className="input input-bordered w-[200px]"
            placeholder="password baru"
            value={pwNew}
            onChange={(e) => setPwNew(e.target.value)}
          />
        </SettingRow>
        <div className="mt-4 flex items-center gap-3">
          <button type="button" className="btn btn-primary btn-sm" onClick={handleChangePassword}>
            Ganti Password
          </button>
          {pwMsg && <span className={`text-sm ${pwMsg.ok ? 'text-success' : 'text-error'}`}>{pwMsg.text}</span>}
        </div>
      </div>
    </div>
  );
}
