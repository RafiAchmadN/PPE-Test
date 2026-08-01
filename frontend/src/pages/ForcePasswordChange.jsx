import { useState } from 'react';
import * as api from '../lib/api';
import { useAuth } from '../context/AuthContext';

export default function ForcePasswordChange() {
  const { refresh } = useAuth();
  const [pwCurrent, setPwCurrent] = useState('');
  const [pwNew, setPwNew] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await api.changePassword(pwCurrent, pwNew);
      await refresh();
    } catch (err) {
      setError(err.message || 'Gagal mengubah password');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-200">
      <div className="card w-[420px] max-w-[90vw] bg-base-100 shadow-xl">
        <div className="card-body p-10">
          <h1 className="text-xl font-bold text-center mb-1">Ganti Password Default</h1>
          <p className="text-sm text-base-content/60 text-center mb-8">
            Demi keamanan, password default harus diganti sebelum melanjutkan.
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">
                Password Saat Ini
              </label>
              <input
                type="password"
                className="input input-bordered w-full"
                autoComplete="current-password"
                required
                value={pwCurrent}
                onChange={(e) => setPwCurrent(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">
                Password Baru (min. 6 karakter)
              </label>
              <input
                type="password"
                className="input input-bordered w-full"
                autoComplete="new-password"
                required
                minLength={6}
                value={pwNew}
                onChange={(e) => setPwNew(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary w-full mt-2" disabled={loading}>
              {loading ? <span className="loading loading-spinner loading-sm"></span> : 'Ganti Password'}
            </button>
            {error && <div className="text-error text-sm text-center min-h-5">{error}</div>}
          </form>
        </div>
      </div>
    </div>
  );
}
