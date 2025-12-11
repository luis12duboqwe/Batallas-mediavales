import { Link, useNavigate } from 'react-router-dom';
import { useUserStore } from '../store/userStore';
import SoundToggle from './SoundToggle';

const Navbar = () => {
  const navigate = useNavigate();
  const { user, logout } = useUserStore();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <nav className="flex items-center justify-between px-6 py-3 bg-gray-950/70 border-b border-yellow-800/40 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-full bg-yellow-600 text-black font-display flex items-center justify-center shadow-glow">BM</div>
        <div>
          <Link to="/" className="text-xl font-display">Batalla Medieval</Link>
          <p className="text-xs text-gray-400">Estratégia en tiempo real</p>
        </div>
      </div>
      {user && (
        <div className="flex items-center gap-4">
          <SoundToggle />
          <span className="text-sm text-gray-300">{user.username}</span>
          <button onClick={handleLogout} className="btn-primary text-sm">Salir</button>
        </div>
      )}
    </nav>
  );
};

export default Navbar;
