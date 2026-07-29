import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await login(username, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message || 'Login gagal');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-200">
      <div className="card w-[380px] max-w-[90vw] bg-base-100 shadow-xl">
        <div className="card-body p-10">
          <img src="/heti-logo.png" alt="HETI" className="h-12 w-auto mx-auto mb-6" />
          <h1 className="text-xl font-bold text-center mb-1">PPE Monitoring System</h1>
          <p className="text-sm text-base-content/60 text-center mb-8">Masuk untuk mengakses dashboard</p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label className="block text-xs uppercase tracking-wide text-base-content/60 mb-1.5">Username</label>
              <input
                type="text"
                className="input input-bordered w-full"
                placeholder="admin"
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
                placeholder="••••••••"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <button type="submit" className="btn btn-primary w-full mt-2" disabled={loading}>
              {loading ? <span className="loading loading-spinner loading-sm"></span> : 'Masuk'}
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
