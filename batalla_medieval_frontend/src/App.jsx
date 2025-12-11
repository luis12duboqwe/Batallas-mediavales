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
import BattleSimulator from './pages/BattleSimulator';
import { useUserStore } from './store/userStore';
import soundManager from './services/sound';

const sidebarLinks = [
  { to: '/', label: 'Ciudad', icon: '🏰' },
  { to: '/buildings', label: 'Edificios', icon: '🛠️' },
  { to: '/troops', label: 'Tropas', icon: '⚔️' },
  { to: '/movements', label: 'Movimientos', icon: '🧭' },
  { to: '/map', label: 'Mapa', icon: '🗺️' },
  { to: '/reports', label: 'Reportes', icon: '📜' },
  { to: '/simulator', label: 'Simulador', icon: '🎯' },
  { to: '/alliance', label: 'Alianza', icon: '🤝' },
  { to: '/messages', label: 'Mensajes', icon: '✉️' },
  { to: '/admin', label: 'Admin', icon: '👑' },
];

const Layout = ({ children }) => {
  const location = useLocation();
  return (
    <div className="min-h-screen bg-gradient-to-br from-midnight via-gray-950 to-black text-gray-100">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(252,211,77,0.12),transparent_35%),radial-gradient(circle_at_80%_0%,rgba(248,180,0,0.08),transparent_30%)]" />
      <Navbar />
      <ResourceBar />
      <div className="flex">
        <aside className="w-64 bg-gray-950/75 border-r border-yellow-800/30 p-4 hidden md:block backdrop-blur-lg">
          <div className="mb-4 text-xs uppercase tracking-[0.2em] text-gray-500">Navegación</div>
          <nav className="space-y-1">
            {sidebarLinks.map((link) => {
              const active = location.pathname === link.to;
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg transition duration-150 border border-transparent ${
                    active
                      ? 'bg-yellow-500/10 text-yellow-200 border-yellow-700 shadow-[0_0_0_1px_rgba(234,179,8,0.3)]'
                      : 'text-gray-300 hover:text-yellow-200 hover:bg-gray-800/60'
                  }`}
                >
                  <span className="text-lg" aria-hidden>{link.icon}</span>
                  <span className="font-medium">{link.label}</span>
                </Link>
              );
            })}
          </nav>
        </aside>
        <main className="flex-1 p-4 md:p-8 space-y-6 relative overflow-hidden">
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_50%_20%,rgba(255,215,128,0.03),transparent_35%)]" />
          <div className="relative animate-fade-in">{children}</div>
        </main>
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
        path="/simulator"
        element={
          <ProtectedRoute>
            <Layout>
              <BattleSimulator />
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
