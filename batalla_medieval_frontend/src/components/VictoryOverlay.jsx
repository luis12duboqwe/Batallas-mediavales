import { useEffect, useState } from 'react';
import { useWorldStore } from '../store/worldStore';
import { useUserStore } from '../store/userStore';
import { api } from '../api/axiosClient';

const VictoryOverlay = () => {
  const { worlds, currentWorldId } = useWorldStore();
  const { user } = useUserStore();
  const [winnerName, setWinnerName] = useState('');
  
  const currentWorld = worlds.find(w => w.id === currentWorldId);

  useEffect(() => {
    if (currentWorld && !currentWorld.is_active && currentWorld.winner) {
      setWinnerName(currentWorld.winner.username);
    }
  }, [currentWorld]);

  if (!currentWorld || currentWorld.is_active) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm animate-fade-in">
      <div className="max-w-2xl w-full p-8 text-center space-y-8">
        <div className="space-y-4">
          <h1 className="text-6xl font-bold text-transparent bg-clip-text bg-gradient-to-b from-yellow-300 to-yellow-600 drop-shadow-[0_5px_5px_rgba(0,0,0,0.8)]">
            ¡VICTORIA!
          </h1>
          <p className="text-2xl text-gray-300">El mundo ha llegado a su fin.</p>
        </div>

        <div className="py-12 relative">
          <div className="absolute inset-0 flex items-center justify-center opacity-20">
            <span className="text-9xl">👑</span>
          </div>
          <div className="relative z-10">
            <p className="text-xl text-yellow-500 uppercase tracking-widest mb-2">Ganador del Servidor</p>
            <p className="text-4xl font-bold text-white">
              {winnerName || `Lord #${currentWorld.winner_id}`}
            </p>
            {currentWorld.winner_id === user?.id && (
              <div className="mt-4 inline-block px-6 py-2 bg-yellow-500/20 border border-yellow-500 rounded-full text-yellow-200 animate-pulse">
                ¡Eres tú! ¡Gloria eterna!
              </div>
            )}
          </div>
        </div>

        <div className="text-gray-400">
          <p>Este mundo ha sido cerrado. Puedes unirte a un nuevo mundo para comenzar una nueva conquista.</p>
        </div>

        <button 
          onClick={() => window.location.href = '/'}
          className="btn-primary px-8 py-3 text-lg"
        >
          Volver al Lobby
        </button>
      </div>
    </div>
  );
};

export default VictoryOverlay;
