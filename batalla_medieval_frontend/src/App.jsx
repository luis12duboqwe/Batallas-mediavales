import { useEffect } from 'react';
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import ResourceBar from './components/ResourceBar';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import CityView from './pages/CityView';
import BuildingsView from './pages/BuildingsView';
import TroopsView from './pages/TroopsView';
import MovementsView from './pages/MovementsView';
import MapView from './pages/MapView';
import ReportsView from './pages/ReportsView';
import AllianceView from './pages/AllianceView';
import MessagesView from './pages/MessagesView';
import AdminPanel from './pages/AdminPanel';
import { useUserStore } from './store/userStore';
import soundManager from './services/sound';

const sidebarLinks = [
  { to: '/', label: 'Ciudad' },
  { to: '/buildings', label: 'Edificios' },
  { to: '/troops', label: 'Tropas' },
  { to: '/movements', label: 'Movimientos' },
  { to: '/map', label: 'Mapa' },
  { to: '/reports', label: 'Reportes' },
  { to: '/alliance', label: 'Alianza' },
  { to: '/messages', label: 'Mensajes' },
  { to: '/admin', label: 'Admin' },
];

const Layout = ({ children }) => {
  const location = useLocation();
  return (
    <div className="min-h-screen bg-gradient-to-br from-midnight via-gray-950 to-black text-gray-100">
      <Navbar />
      <ResourceBar />
      <div className="flex">
        <aside className="w-64 bg-gray-950/80 border-r border-yellow-800/30 p-4 hidden md:block">
          <nav className="space-y-2">
            {sidebarLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`block px-3 py-2 rounded hover:bg-gray-800 transition ${
                  location.pathname === link.to ? 'bg-gray-800 text-yellow-300' : 'text-gray-300'
                }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="flex-1 p-4 md:p-8 space-y-6">{children}</main>
      </div>
    </div>
  );
};

const ProtectedRoute = ({ children }) => {
  const { isAuthenticated } = useUserStore();
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  return children;
};

const App = () => {
  const { token, refreshCity } = useUserStore();
  const location = useLocation();

  useEffect(() => {
    if (token) {
      refreshCity().catch(() => {});
    }
  }, [token, refreshCity]);

  useEffect(() => {
    const handleClick = (event) => {
      const target = event.target;
      if (target instanceof Element && target.closest('button')) {
        soundManager.playSFX('click_ui');
      }
    };
    document.addEventListener('click', handleClick, true);
    return () => document.removeEventListener('click', handleClick, true);
  }, []);

  useEffect(() => {
    const isMapView = location.pathname.startsWith('/map');
    soundManager.playMusic(isMapView ? 'war_drums' : 'calm_medieval');
  }, [location.pathname]);

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout>
              <Dashboard />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/buildings"
        element={
          <ProtectedRoute>
            <Layout>
              <BuildingsView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/troops"
        element={
          <ProtectedRoute>
            <Layout>
              <TroopsView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/movements"
        element={
          <ProtectedRoute>
            <Layout>
              <MovementsView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/map"
        element={
          <ProtectedRoute>
            <Layout>
              <MapView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reports"
        element={
          <ProtectedRoute>
            <Layout>
              <ReportsView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/alliance"
        element={
          <ProtectedRoute>
            <Layout>
              <AllianceView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/messages"
        element={
          <ProtectedRoute>
            <Layout>
              <MessagesView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <ProtectedRoute>
            <Layout>
              <AdminPanel />
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
};

export default App;
