import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';

// Code-split per halaman — sebelumnya semua page (termasuk chart/table di
// Dashboard & Logs) di-bundle jadi satu file JS yang harus diunduh penuh
// sebelum layar login pun sempat tampil. Tiap import() di bawah jadi chunk
// terpisah yang baru diambil browser saat route-nya benar-benar dikunjungi.
const Login = lazy(() => import('./pages/Login'));
const ForcePasswordChange = lazy(() => import('./pages/ForcePasswordChange'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const LiveCameras = lazy(() => import('./pages/LiveCameras'));
const CameraManagement = lazy(() => import('./pages/CameraManagement'));
const Logs = lazy(() => import('./pages/Logs'));
const Settings = lazy(() => import('./pages/Settings'));

function FullScreenSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-base-200">
      <span className="loading loading-spinner loading-lg text-primary"></span>
    </div>
  );
}

function ProtectedLayout() {
  const { status, mustChangePassword } = useAuth();
  if (status === 'loading') return <FullScreenSpinner />;
  if (status === 'guest') return <Navigate to="/login" replace />;
  if (mustChangePassword) return <ForcePasswordChange />;
  return (
    <div className="flex h-screen overflow-hidden bg-base-200">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Topbar />
        <div className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </div>
      </div>
    </div>
  );
}

function PublicOnlyRoute({ children }) {
  const { status } = useAuth();
  if (status === 'loading') return <FullScreenSpinner />;
  if (status === 'authed') return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    // basename WAJIB disamakan dengan Vite `base` (vite.config.js) — tanpa ini,
    // refresh/reload di path manapun selain "/" (mis. /ppe/cameras) tidak
    // cocok dengan route manapun, jatuh ke catch-all, lalu <Navigate to="/">
    // menulis URL ABSOLUT root domain (kehilangan prefix /ppe) alih-alih /ppe/.
    // import.meta.env.BASE_URL otomatis ikut nilai `base` yang sama dipakai
    // asset (termasuk override VITE_BASE kalau suatu saat pindah subpath).
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <AuthProvider>
        <Suspense fallback={<FullScreenSpinner />}>
          <Routes>
            <Route
              path="/login"
              element={
                <PublicOnlyRoute>
                  <Login />
                </PublicOnlyRoute>
              }
            />
            <Route path="/" element={<ProtectedLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="cameras" element={<LiveCameras />} />
              <Route path="manage" element={<CameraManagement />} />
              <Route path="logs" element={<Logs />} />
              <Route path="settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}
