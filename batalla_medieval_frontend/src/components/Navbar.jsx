import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../store/userStore';
import SoundToggle from './SoundToggle';

const Navbar = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout, isAuthenticated } = useUserStore();
  const authenticated = isAuthenticated();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <nav
      className="flex items-center justify-between gap-2 px-3 sm:px-6 py-3 bg-gray-950/80 border-b border-yellow-800/40 backdrop-blur-xl shadow-[0_8px_30px_rgba(0,0,0,0.45)] sticky top-0 z-40"
      aria-label={t('nav.top_navigation')}
    >
      <Link
        to="/"
        className="flex min-w-0 items-center gap-2 sm:gap-3 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
        aria-label={t('brand.home_label')}
      >
        <div className="h-9 w-9 sm:h-11 sm:w-11 shrink-0 rounded-full bg-gradient-to-br from-amber-500 via-yellow-500 to-amber-700 text-black font-display flex items-center justify-center shadow-[0_0_0_3px_rgba(234,179,8,0.4)]">
          BM
        </div>
        <div className="min-w-0">
          <span className="block truncate text-base sm:text-xl font-display leading-none">{t('brand.name')}</span>
          <p className="hidden sm:block text-xs text-gray-400">{t('brand.tagline')}</p>
        </div>
      </Link>

      {authenticated && (
        <div className="flex shrink-0 items-center gap-2 sm:gap-4">
          <SoundToggle />
          <Link
            to="/profile"
            className="hidden sm:inline rounded text-sm text-gray-200 hover:text-amber-400 font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
          >
            {user?.username || t('nav.profile')}
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            data-testid="logout-button"
            className="btn-ghost text-xs sm:text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400"
          >
            {t('nav.logout')}
          </button>
        </div>
      )}
    </nav>
  );
};

export default Navbar;
