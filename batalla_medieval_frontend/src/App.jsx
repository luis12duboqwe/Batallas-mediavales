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
import CityView from './pages/CityView';
import BuildingsView from './pages/BuildingsView';
import TroopsView from './pages/TroopsView';
import MovementsView from './pages/MovementsView';
import MapView from './pages/MapView';
import ReportsView from './pages/ReportsView';
import AllianceView from './pages/AllianceView';
import MessagesView from './pages/MessagesView';
import QuestsView from './pages/QuestsView';
import RankingView from './pages/RankingView';
import ShopView from './pages/ShopView';
import WikiView from './pages/WikiView';
import ProfileView from './pages/ProfileView';
import AdminPanel from './pages/AdminPanel';
import BattleSimulator from './pages/BattleSimulator';
import MarketView from './pages/MarketView';
import AcademyView from './pages/AcademyView';
import HeroView from './pages/HeroView';
import AdventuresView from './pages/AdventuresView';
import SendMovementView from './pages/SendMovementView';
import ChatWidget from './components/ChatWidget';
import TutorialOverlay from './components/TutorialOverlay';
import VictoryOverlay from './components/VictoryOverlay';
import NotificationListener from './components/NotificationListener';
import { useUserStore } from './store/userStore';
import soundManager from './services/sound';

import { useTranslation } from 'react-i18next';

const sidebarLinks = [
  { to: '/', key: 'nav.city', icon: '🏰' },
  { to: '/buildings', key: 'nav.buildings', icon: '🛠️' },
  { to: '/troops', key: 'nav.troops', icon: '⚔️' },
  { to: '/hero', key: 'nav.hero', icon: '🦸' },
  { to: '/adventures', key: 'nav.adventures', icon: '🏕️' },
  { to: '/academy', key: 'nav.academy', icon: '🎓' },
  { to: '/market', key: 'nav.market', icon: '⚖️' },
  { to: '/movements', key: 'nav.movements', icon: '🧭' },
  { to: '/map', key: 'nav.map', icon: '🗺️' },
  { to: '/reports', key: 'nav.reports', icon: '📜' },
  { to: '/quests', key: 'nav.quests', icon: '📜' },
  { to: '/ranking', key: 'nav.ranking', icon: '🏆' },
  { to: '/alliance', key: 'nav.alliance', icon: '🤝' },
  { to: '/shop', key: 'nav.shop', icon: '💎' },
  { to: '/wiki', key: 'nav.wiki', icon: '❓' },
  { to: '/messages', key: 'nav.messages', icon: '✉️' },
  { to: '/simulator', key: 'nav.simulator', icon: '🎯' },
];

const Layout = ({ children }) => {
  const { t } = useTranslation();
  const location = useLocation();
  return (
    <div className="min-h-screen bg-gradient-to-br from-midnight via-gray-950 to-black text-gray-100">
      <VictoryOverlay />
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
      <ChatWidget />
      <NotificationListener />
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
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
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
        path="/profile"
        element={
          <ProtectedRoute>
            <Layout>
              <ProfileView />
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
        path="/hero"
        element={
          <ProtectedRoute>
            <Layout>
              <HeroView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/adventures"
        element={
          <ProtectedRoute>
            <Layout>
              <AdventuresView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/academy"
        element={
          <ProtectedRoute>
            <Layout>
              <AcademyView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/market"
        element={
          <ProtectedRoute>
            <Layout>
              <MarketView />
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
        path="/quests"
        element={
          <ProtectedRoute>
            <Layout>
              <QuestsView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/ranking"
        element={
          <ProtectedRoute>
            <Layout>
              <RankingView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/shop"
        element={
          <ProtectedRoute>
            <Layout>
              <ShopView />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/wiki"
        element={
          <ProtectedRoute>
            <Layout>
              <WikiView />
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
        path="/send-movement/:targetCityId"
        element={
          <ProtectedRoute>
            <Layout>
              <SendMovementView />
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
