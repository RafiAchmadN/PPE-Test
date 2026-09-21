import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { asset } from '../lib/assets';
import * as api from '../lib/api';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function switchMode(next) {
    setMode(next);
    setError('');
    setPassword('');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      if (mode === 'signup') {
        await api.register(username, password);
        // Langsung login pakai kredensial yang baru dibuat -- akun signup
        // selalu role 'user' (dipaksa di backend, tidak bisa jadi admin).
        await login(username, password);
      } else {
        await login(username, password);
      }
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message || (mode === 'signup' ? 'Pendaftaran gagal' : 'Login gagal'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-200">
      <div className="card w-[380px] max-w-[90vw] bg-base-100 shadow-xl">
        <div className="card-body p-10">
          <img src={asset('heti-logo.png')} alt="HETI" className="h-12 w-auto mx-auto mb-6" />
          <h1 className="text-xl font-bold text-center mb-1">PPE Monitoring System</h1>
          <p className="text-sm text-base-content/60 text-center mb-6">
            {mode === 'signup' ? 'Daftar akun baru (role viewer)' : 'Masuk untuk mengakses dashboard'}
          </p>

          <div className="tabs tabs-boxed mb-6 bg-base-200">
            <button
              type="button"
              className={`tab flex-1 ${mode === 'login' ? 'tab-active' : ''}`}
              onClick={() => switchMode('login')}
            >
              Masuk
            </button>
            <button
              type="button"
              className={`tab flex-1 ${mode === 'signup' ? 'tab-active' : ''}`}
              onClick={() => switchMode('signup')}
            >
              Daftar
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Email</label>
              <input
                type="email"
                className="input input-bordered w-full"
                placeholder="nama@contoh.com"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Password</label>
              <input
                type="password"
                className="input input-bordered w-full"
                placeholder={mode === 'signup' ? 'min. 8 karakter' : '••••••••'}
                autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                required
                minLength={mode === 'signup' ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary w-full mt-2" disabled={loading}>
              {loading ? (
                <span className="loading loading-spinner loading-sm"></span>
              ) : mode === 'signup' ? (
                'Daftar & Masuk'
              ) : (
                'Masuk'
              )}
            </button>
            {error && <div className="text-error text-sm text-center min-h-5">{error}</div>}
          </form>

          <div className="mt-8 text-center text-[11px] text-base-content/40 font-mono-app">
            ITS Surabaya &nbsp;·&nbsp; PPE Detection v1.0
          </div>
        </div>
      </div>
    </div>
  );
}
