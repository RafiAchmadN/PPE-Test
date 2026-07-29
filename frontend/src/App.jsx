import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import LiveCameras from './pages/LiveCameras';
import CameraManagement from './pages/CameraManagement';
import Logs from './pages/Logs';
import Settings from './pages/Settings';

function FullScreenSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-base-200">
      <span className="loading loading-spinner loading-lg text-primary"></span>
    </div>
  );
}

function ProtectedLayout() {
  const { status } = useAuth();
  if (status === 'loading') return <FullScreenSpinner />;
  if (status === 'guest') return <Navigate to="/login" replace />;
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
    <BrowserRouter>
      <AuthProvider>
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
      </AuthProvider>
    </BrowserRouter>
  );
}
