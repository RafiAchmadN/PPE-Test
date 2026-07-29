import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import * as api from '../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // 'loading' | 'authed' | 'guest'
  const [status, setStatus] = useState('loading');

  const checkAuth = useCallback(async () => {
    try {
      const r = await api.authStatus();
      setStatus(r?.logged_in ? 'authed' : 'guest');
    } catch {
      setStatus('guest');
    }
  }, []);

  useEffect(() => {
    api.setUnauthorizedHandler(() => setStatus('guest'));
    checkAuth();
  }, [checkAuth]);

  async function doLogin(username, password) {
    await api.login(username, password);
    setStatus('authed');
  }

  async function doLogout() {
    try {
      await api.logout();
    } finally {
      setStatus('guest');
    }
  }

  return (
    <AuthContext.Provider value={{ status, login: doLogin, logout: doLogout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
