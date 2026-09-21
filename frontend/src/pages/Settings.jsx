import { useEffect, useState } from 'react';
import * as api from '../lib/api';
import { useAuth } from '../context/AuthContext';

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

function UserManagementCard() {
  const { username: myUsername } = useAuth();
  const [users, setUsers] = useState(null);
  const [err, setErr] = useState('');
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'user' });
  const [creating, setCreating] = useState(false);

  function load() {
    api.getUsers().then(setUsers).catch((e) => setErr(e.message || 'Gagal memuat akun'));
  }

  useEffect(load, []);

  async function handleCreate(e) {
    e.preventDefault();
    setErr('');
    setCreating(true);
    try {
      await api.createUser(newUser);
      setNewUser({ username: '', password: '', role: 'user' });
      load();
    } catch (e) {
      setErr(e.message || 'Gagal membuat akun');
    } finally {
      setCreating(false);
    }
  }

  async function handleRoleToggle(u) {
    const nextRole = u.role === 'admin' ? 'user' : 'admin';
    if (!confirm(`Ubah role "${u.username}" jadi ${nextRole}?`)) return;
    setErr('');
    try {
      await api.updateUser(u.id, { role: nextRole });
      load();
    } catch (e) {
      setErr(e.message || 'Gagal ubah role');
    }
  }

  async function handleResetPassword(u) {
    const pw = prompt(`Password baru untuk "${u.username}" (min. 8 karakter):`);
    if (!pw) return;
    setErr('');
    try {
      await api.updateUser(u.id, { password: pw });
      load();
    } catch (e) {
      setErr(e.message || 'Gagal reset password');
    }
  }

  async function handleDelete(u) {
    if (!confirm(`Hapus akun "${u.username}"? Tidak bisa dibatalkan.`)) return;
    setErr('');
    try {
      await api.deleteUser(u.id);
      load();
    } catch (e) {
      setErr(e.message || 'Gagal menghapus akun');
    }
  }

  return (
    <div className="card bg-base-100 border border-base-300 shadow-sm p-6 mt-5">
      <h3 className="text-sm font-semibold mb-4 flex items-center gap-2">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-primary">
          <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 00-3-3.87" />
          <path d="M16 3.13a4 4 0 010 7.75" />
        </svg>
        Manajemen Akun
      </h3>

      {!users ? (
        <div className="flex justify-center py-8">
          <span className="loading loading-spinner text-primary"></span>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Dibuat</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="font-mono-app">
                    {u.username}
                    {u.username === myUsername && <span className="text-base-content/40 text-xs"> (kamu)</span>}
                  </td>
                  <td>
                    <span className={`badge badge-sm ${u.role === 'admin' ? 'badge-primary' : 'badge-ghost'}`}>{u.role}</span>
                  </td>
                  <td className="text-xs text-base-content/50">{u.created_at}</td>
                  <td>
                    <div className="flex gap-1 justify-end">
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs"
                        onClick={() => handleRoleToggle(u)}
                        title="Ubah role"
                      >
                        {u.role === 'admin' ? 'Jadikan user' : 'Jadikan admin'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs"
                        onClick={() => handleResetPassword(u)}
                        title="Reset password"
                      >
                        Reset PW
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs text-error"
                        onClick={() => handleDelete(u)}
                        disabled={u.username === myUsername}
                        title={u.username === myUsername ? 'Tidak bisa hapus akun sendiri' : 'Hapus akun'}
                      >
                        Hapus
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-2 mt-5 pt-4 border-t border-base-300">
        <div>
          <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Email Baru</label>
          <input
            type="email"
            className="input input-bordered input-sm w-[200px]"
            placeholder="nama@contoh.com"
            required
            value={newUser.username}
            onChange={(e) => setNewUser((s) => ({ ...s, username: e.target.value }))}
          />
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Password</label>
          <input
            type="password"
            className="input input-bordered input-sm w-[160px]"
            minLength={8}
            required
            value={newUser.password}
            onChange={(e) => setNewUser((s) => ({ ...s, password: e.target.value }))}
          />
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Role</label>
          <select
            className="select select-bordered select-sm"
            value={newUser.role}
            onChange={(e) => setNewUser((s) => ({ ...s, role: e.target.value }))}
          >
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </div>
        <button type="submit" className="btn btn-primary btn-sm" disabled={creating}>
          {creating ? <span className="loading loading-spinner loading-xs"></span> : 'Tambah Akun'}
        </button>
      </form>
      {err && <div className="text-error text-sm mt-3">{err}</div>}
    </div>
  );
}

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState(false);
  const [settingsErr, setSettingsErr] = useState('');

  useEffect(() => {
    api.getSettings().then(setSettings);
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
        <SettingRow label="Stream FPS (base)" desc="Target fps saat 4 kamera aktif bersamaan — otomatis naik jika kamera aktif sedikit, turun jika banyak (2-15 fps)">
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

      <UserManagementCard />
    </div>
  );
}
