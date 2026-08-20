import { useEffect } from 'react';
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import ResourceBar from './components/ResourceBar';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import VerifyEmail from './pages/VerifyEmail';
import Dashboard from './pages/Dashboard';
import BuildingsView from './pages/BuildingsView';
import TroopsView from './pages/TroopsView';
import MovementsView from './pages/MovementsView';
import MapView from './pages/MapView';
import ReportsView from './pages/ReportsView';
import AllianceView from './pages/AllianceView';
import MessagesView from './pages/MessagesView';
import RankingView from './pages/RankingView';
import ProfileView from './pages/ProfileView';
import AdminPanel from './pages/AdminPanel';
import MarketView from './pages/MarketView';
import AcademyView from './pages/AcademyView';
import SendMovementView from './pages/SendMovementView';
import TutorialOverlay from './components/TutorialOverlay';
import { useUserStore } from './store/userStore';
import soundManager from './services/sound';
import { useTranslation } from 'react-i18next';

const sidebarLinks = [
  { to: '/', key: 'nav.city', icon: '🏰' },
  { to: '/buildings', key: 'nav.buildings', icon: '🛠️' },
  { to: '/academy', key: 'nav.academy', icon: '🎓' },
  { to: '/troops', key: 'nav.troops', icon: '⚔️' },
  { to: '/map', key: 'nav.map', icon: '🗺️' },
  { to: '/movements', key: 'nav.movements', icon: '🧭' },
  { to: '/reports', key: 'nav.reports', icon: '📜' },
  { to: '/market', key: 'nav.market', icon: '⚖️' },
  { to: '/ranking', key: 'nav.ranking', icon: '🏆' },
  { to: '/alliance', key: 'nav.alliance', icon: '🤝' },
  { to: '/messages', key: 'nav.messages', icon: '✉️' },
];

const Layout = ({ children }) => {
  const { t } = useTranslation();
  const location = useLocation();
  return (
    <div className="min-h-screen bg-gradient-to-br from-midnight via-gray-950 to-black text-gray-100">
      <TutorialOverlay />
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
                  <span className="font-medium">{t(link.key)}</span>
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

const AdminRoute = ({ children }) => {
  const { user, isAuthenticated } = useUserStore();
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  if (!user) return null;
  if (!user.is_admin) return <Navigate to="/" replace />;
  return children;
};

const GameRoute = ({ children }) => (
  <ProtectedRoute>
    <Layout>{children}</Layout>
  </ProtectedRoute>
);

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
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />

      <Route path="/" element={<GameRoute><Dashboard /></GameRoute>} />
      <Route path="/profile" element={<GameRoute><ProfileView /></GameRoute>} />
      <Route path="/buildings" element={<GameRoute><BuildingsView /></GameRoute>} />
      <Route path="/academy" element={<GameRoute><AcademyView /></GameRoute>} />
      <Route path="/troops" element={<GameRoute><TroopsView /></GameRoute>} />
      <Route path="/market" element={<GameRoute><MarketView /></GameRoute>} />
      <Route path="/movements" element={<GameRoute><MovementsView /></GameRoute>} />
      <Route path="/map" element={<GameRoute><MapView /></GameRoute>} />
      <Route path="/reports" element={<GameRoute><ReportsView /></GameRoute>} />
      <Route path="/ranking" element={<GameRoute><RankingView /></GameRoute>} />
      <Route path="/alliance" element={<GameRoute><AllianceView /></GameRoute>} />
      <Route path="/messages" element={<GameRoute><MessagesView /></GameRoute>} />
      <Route path="/send-movement/:targetCityId" element={<GameRoute><SendMovementView /></GameRoute>} />

      <Route
        path="/admin"
        element={
          <AdminRoute>
            <Layout><AdminPanel /></Layout>
          </AdminRoute>
        }
      />

      <Route path="*" element={<Navigate to={token ? '/' : '/login'} replace />} />
    </Routes>
  );
};

export default App;
