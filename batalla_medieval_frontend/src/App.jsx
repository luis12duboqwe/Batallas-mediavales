import { lazy, Suspense, useEffect, useRef } from 'react';
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Navbar from './components/Navbar';
import ResourceBar from './components/ResourceBar';
import GameIcon from './components/GameIcon';
import TutorialOverlay from './components/TutorialOverlay';
import RouteLoadBoundary, { recoverableImport } from './components/RouteLoadBoundary';
import { useUserStore } from './store/userStore';
import { useCityStore } from './store/cityStore';
import soundManager from './services/sound';

const Login = lazy(recoverableImport(() => import('./pages/Login'), 'login'));
const Register = lazy(recoverableImport(() => import('./pages/Register'), 'register'));
const ForgotPassword = lazy(recoverableImport(() => import('./pages/ForgotPassword'), 'forgot-password'));
const ResetPassword = lazy(recoverableImport(() => import('./pages/ResetPassword'), 'reset-password'));
const VerifyEmail = lazy(recoverableImport(() => import('./pages/VerifyEmail'), 'verify-email'));
const Dashboard = lazy(recoverableImport(() => import('./pages/Dashboard'), 'dashboard'));
const BuildingsView = lazy(recoverableImport(() => import('./pages/BuildingsView'), 'buildings'));
const TroopsView = lazy(recoverableImport(() => import('./pages/TroopsView'), 'troops'));
const MovementsView = lazy(recoverableImport(() => import('./pages/MovementsView'), 'movements'));
const MapView = lazy(recoverableImport(() => import('./pages/MapView'), 'map'));
const ReportsView = lazy(recoverableImport(() => import('./pages/ReportsView'), 'reports'));
const AllianceView = lazy(recoverableImport(() => import('./pages/AllianceView'), 'alliance'));
const MessagesView = lazy(recoverableImport(() => import('./pages/MessagesView'), 'messages'));
const RankingView = lazy(recoverableImport(() => import('./pages/RankingView'), 'ranking'));
const ProfileView = lazy(recoverableImport(() => import('./pages/ProfileView'), 'profile'));
const AdminPanel = lazy(recoverableImport(() => import('./pages/AdminPanel'), 'admin-panel'));
const AdminCityCreateCard = lazy(recoverableImport(() => import('./pages/AdminCityCreateCard'), 'admin-city-create'));
const MarketView = lazy(recoverableImport(() => import('./pages/MarketView'), 'market'));
const AcademyView = lazy(recoverableImport(() => import('./pages/AcademyView'), 'academy'));
const ExpansionView = lazy(recoverableImport(() => import('./pages/ExpansionView'), 'expansion'));
const SendMovementView = lazy(recoverableImport(() => import('./pages/SendMovementView'), 'send-movement'));
const HeroView = lazy(recoverableImport(() => import('./pages/HeroView'), 'hero'));
const AdventuresView = lazy(recoverableImport(() => import('./pages/AdventuresView'), 'adventures'));
const WikiView = lazy(recoverableImport(() => import('./pages/WikiView'), 'wiki'));

const sidebarLinks = [
  { to: '/', key: 'nav.city', icon: 'castle' },
  { to: '/buildings', key: 'nav.buildings', icon: 'buildings' },
  { to: '/expansion', key: 'nav.expansion', icon: 'camp' },
  { to: '/academy', key: 'nav.academy', icon: 'academy' },
  { to: '/troops', key: 'nav.troops', icon: 'sword' },
  { to: '/hero', key: 'nav.hero', icon: 'hero' },
  { to: '/adventures', key: 'nav.adventures', icon: 'compass' },
  { to: '/map', key: 'nav.map', icon: 'map' },
  { to: '/movements', key: 'nav.movements', icon: 'boot' },
  { to: '/reports', key: 'nav.reports', icon: 'scroll' },
  { to: '/market', key: 'nav.market', icon: 'scales' },
  { to: '/ranking', key: 'nav.ranking', icon: 'trophy' },
  { to: '/alliance', key: 'nav.alliance', icon: 'alliance' },
  { to: '/messages', key: 'nav.messages', icon: 'mail' },
  { to: '/wiki', key: 'nav.wiki', icon: 'book' },
];

const RouteFallback = ({ fullPage = false }) => {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="route-loading"
      className={fullPage
        ? 'min-h-screen flex items-center justify-center bg-midnight text-yellow-100'
        : 'card p-6 text-center text-yellow-100'}
    >
      {t('common.loading')}
    </div>
  );
};

const PageBoundary = ({ children, fullPage = false }) => (
  <RouteLoadBoundary fullPage={fullPage}>
    <Suspense fallback={<RouteFallback fullPage={fullPage} />}>
      {children}
    </Suspense>
  </RouteLoadBoundary>
);

const NavLink = ({ link, active, mobile = false, t }) => (
  <Link
    to={link.to}
    aria-current={active ? 'page' : undefined}
    className={
      mobile
        ? `min-w-[76px] flex flex-col items-center justify-center gap-1 px-2 py-2 text-xs border-t-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400 ${
            active
              ? 'border-yellow-500 bg-yellow-500/10 text-yellow-200'
              : 'border-transparent text-gray-300 hover:text-yellow-200 hover:bg-gray-800/70'
          }`
        : `flex items-center gap-3 px-3 py-2 rounded-lg transition duration-150 border border-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400 ${
            active
              ? 'bg-yellow-500/10 text-yellow-200 border-yellow-700 shadow-[0_0_0_1px_rgba(234,179,8,0.3)]'
              : 'text-gray-300 hover:text-yellow-200 hover:bg-gray-800/60'
          }`
    }
  >
    <GameIcon name={link.icon} size={mobile ? 18 : 20} className="shrink-0" />
    <span className="font-medium whitespace-nowrap">{t(link.key)}</span>
  </Link>
);

const Layout = ({ children }) => {
  const { t } = useTranslation();
  const location = useLocation();
  const mainRef = useRef(null);
  const hasHandledInitialLocationRef = useRef(false);

  useEffect(() => {
    if (!hasHandledInitialLocationRef.current) {
      hasHandledInitialLocationRef.current = true;
      return;
    }
    mainRef.current?.focus({ preventScroll: false });
  }, [location.key, location.pathname]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-midnight via-gray-950 to-black text-gray-100">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-yellow-300 focus:px-4 focus:py-2 focus:font-semibold focus:text-black focus:shadow-xl"
      >
        {t('accessibility.skip_to_content')}
      </a>
      <TutorialOverlay />
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(252,211,77,0.12),transparent_35%),radial-gradient(circle_at_80%_0%,rgba(248,180,0,0.08),transparent_30%)]" />
      <Navbar />
      <ResourceBar />
      <div className="flex">
        <aside className="w-64 bg-gray-950/75 border-r border-yellow-800/30 p-4 hidden md:block backdrop-blur-lg">
          <div className="mb-4 text-xs uppercase tracking-[0.2em] text-gray-500">{t('nav.navigation')}</div>
          <nav className="space-y-1" aria-label={t('nav.navigation')}>
            {sidebarLinks.map((link) => (
              <NavLink key={link.to} link={link} active={location.pathname === link.to} t={t} />
            ))}
          </nav>
        </aside>
        <main
          id="main-content"
          ref={mainRef}
          tabIndex={-1}
          aria-label={t('accessibility.main_content')}
          className="flex-1 min-w-0 p-4 pb-24 md:p-8 md:pb-8 space-y-6 relative overflow-hidden focus:outline-none"
        >
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_50%_20%,rgba(255,215,128,0.03),transparent_35%)]" />
          <div className="relative animate-fade-in">{children}</div>
        </main>
      </div>
      <nav
        className="md:hidden fixed inset-x-0 bottom-0 z-50 border-t border-yellow-800/40 bg-gray-950/95 backdrop-blur-xl shadow-[0_-8px_30px_rgba(0,0,0,0.45)]"
        aria-label={t('nav.mobile_navigation')}
        data-testid="mobile-navigation"
      >
        <div className="flex overflow-x-auto overscroll-x-contain">
          {sidebarLinks.map((link) => (
            <NavLink key={link.to} link={link} active={location.pathname === link.to} mobile t={t} />
          ))}
        </div>
      </nav>
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
    <Layout><PageBoundary>{children}</PageBoundary></Layout>
  </ProtectedRoute>
);

const App = () => {
  const { user, token, refreshCity } = useUserStore();
  const { loadCity } = useCityStore();
  const { i18n } = useTranslation();
  const location = useLocation();

  useEffect(() => {
    if (token) {
      refreshCity().catch(() => {});
      loadCity().catch(() => {});
    }
  }, [token, refreshCity, loadCity]);

  useEffect(() => {
    if (user?.language && i18n.resolvedLanguage !== user.language) {
      i18n.changeLanguage(user.language);
    }
  }, [user?.language, i18n]);

  useEffect(() => {
    const unlockAudio = () => { void soundManager.unlock(); };
    window.addEventListener('pointerdown', unlockAudio, { capture: true });
    window.addEventListener('keydown', unlockAudio, { capture: true });
    return () => {
      window.removeEventListener('pointerdown', unlockAudio, true);
      window.removeEventListener('keydown', unlockAudio, true);
    };
  }, []);

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
    if (!token) {
      void soundManager.deactivate();
      return;
    }
    const isMapView = location.pathname.startsWith('/map');
    soundManager.playMusic(isMapView ? 'war_drums' : 'calm_medieval');
  }, [token, location.pathname]);

  return (
    <Routes>
      <Route path="/login" element={<PageBoundary fullPage><Login /></PageBoundary>} />
      <Route path="/register" element={<PageBoundary fullPage><Register /></PageBoundary>} />
      <Route path="/forgot-password" element={<PageBoundary fullPage><ForgotPassword /></PageBoundary>} />
      <Route path="/reset-password" element={<PageBoundary fullPage><ResetPassword /></PageBoundary>} />
      <Route path="/verify-email" element={<PageBoundary fullPage><VerifyEmail /></PageBoundary>} />

      <Route path="/" element={<GameRoute><Dashboard /></GameRoute>} />
      <Route path="/profile" element={<GameRoute><ProfileView /></GameRoute>} />
      <Route path="/buildings" element={<GameRoute><BuildingsView /></GameRoute>} />
      <Route path="/expansion" element={<GameRoute><ExpansionView /></GameRoute>} />
      <Route path="/academy" element={<GameRoute><AcademyView /></GameRoute>} />
      <Route path="/troops" element={<GameRoute><TroopsView /></GameRoute>} />
      <Route path="/hero" element={<GameRoute><HeroView /></GameRoute>} />
      <Route path="/adventures" element={<GameRoute><AdventuresView /></GameRoute>} />
      <Route path="/market" element={<GameRoute><MarketView /></GameRoute>} />
      <Route path="/movements" element={<GameRoute><MovementsView /></GameRoute>} />
      <Route path="/map" element={<GameRoute><MapView /></GameRoute>} />
      <Route path="/reports" element={<GameRoute><ReportsView /></GameRoute>} />
      <Route path="/ranking" element={<GameRoute><RankingView /></GameRoute>} />
      <Route path="/alliance" element={<GameRoute><AllianceView /></GameRoute>} />
      <Route path="/messages" element={<GameRoute><MessagesView /></GameRoute>} />
      <Route path="/wiki" element={<GameRoute><WikiView /></GameRoute>} />
      <Route path="/send-movement/:targetCityId" element={<GameRoute><SendMovementView /></GameRoute>} />

      <Route
        path="/admin"
        element={
          <AdminRoute>
            <Layout>
              <PageBoundary>
                <AdminPanel />
                <AdminCityCreateCard />
              </PageBoundary>
            </Layout>
          </AdminRoute>
        }
      />

      <Route path="*" element={<Navigate to={token ? '/' : '/login'} replace />} />
    </Routes>
  );
};

export default App;
