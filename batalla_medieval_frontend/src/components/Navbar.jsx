import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../store/userStore';
import SoundToggle from './SoundToggle';

const Navbar = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, logout } = useUserStore();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <nav className="flex items-center justify-between px-6 py-3 bg-gray-950/80 border-b border-yellow-800/40 backdrop-blur-xl shadow-[0_8px_30px_rgba(0,0,0,0.45)] sticky top-0 z-40">
      <div className="flex items-center gap-3">
        <Link to="/" className="flex items-center gap-3">
          <div className="h-11 w-11 rounded-full bg-gradient-to-br from-amber-500 via-yellow-500 to-amber-700 text-black font-display flex items-center justify-center shadow-[0_0_0_3px_rgba(234,179,8,0.4)]">
            BM
          </div>
          <div>
            <span className="text-xl font-display leading-none">Batalla Medieval</span>
            <p className="text-xs text-gray-400">Estrategia en tiempo real</p>
          </div>
        </Link>
      </div>
      {user && (
        <div className="flex items-center gap-4">
          <SoundToggle />
          <Link to="/profile" className="text-sm text-gray-200 hover:text-amber-400 font-bold">
            {user.username}
          </Link>
          <button onClick={handleLogout} className="btn-ghost text-sm">{t('nav.logout')}</button>
        </div>
      )}
    </nav>
  );
};

export default Navbar;
