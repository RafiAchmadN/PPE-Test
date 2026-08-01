import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import * as api from '../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // 'loading' | 'authed' | 'guest'
  const [status, setStatus] = useState('loading');
  const [mustChangePassword, setMustChangePassword] = useState(false);

  const checkAuth = useCallback(async () => {
    try {
      const r = await api.authStatus();
      setStatus(r?.logged_in ? 'authed' : 'guest');
      setMustChangePassword(!!r?.must_change_password);
    } catch {
      setStatus('guest');
      setMustChangePassword(false);
    }
  }, []);

  useEffect(() => {
    api.setUnauthorizedHandler(() => setStatus('guest'));
    checkAuth();
  }, [checkAuth]);

  async function doLogin(username, password) {
    await api.login(username, password);
    await checkAuth();
  }

  async function doLogout() {
    try {
      await api.logout();
    } finally {
      setStatus('guest');
      setMustChangePassword(false);
    }
  }

  return (
    <AuthContext.Provider value={{ status, mustChangePassword, login: doLogin, logout: doLogout, refresh: checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
