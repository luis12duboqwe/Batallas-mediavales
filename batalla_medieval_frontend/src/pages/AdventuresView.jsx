import { useState, useEffect } from 'react';
import { api } from '../api/axiosClient';
import Timer from '../components/Timer';
import { useUserStore } from '../store/userStore';

const AdventuresView = () => {
  const [adventures, setAdventures] = useState([]);
  const [loading, setLoading] = useState(false);
  const [claimResult, setClaimResult] = useState(null);
  const { user } = useUserStore();

  useEffect(() => {
    fetchAdventures();
  }, []);

  const fetchAdventures = async () => {
    setLoading(true);
    try {
      const res = await api.getAdventures();
      setAdventures(res.data);
    } catch (error) {
      console.error("Failed to load adventures", error);
    } finally {
      setLoading(false);
    }
  };

  const handleStart = async (id) => {
    try {
      await api.startAdventure(id);
      fetchAdventures();
    } catch (error) {
      alert(error.response?.data?.detail || "Error starting adventure");
    }
  };

  const handleClaim = async (id) => {
    try {
      const res = await api.claimAdventure(id);
      setClaimResult(res.data);
      fetchAdventures();
    } catch (error) {
      alert(error.response?.data?.detail || "Error claiming adventure");
    }
  };

  const getDifficultyColor = (diff) => {
    switch (diff) {
      case 'easy': return 'text-green-400';
      case 'medium': return 'text-yellow-400';
      case 'hard': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-6 text-amber-500">Aventuras</h1>
      <p className="text-gray-400 mb-8">Envía a tu héroe a misiones peligrosas para obtener experiencia y objetos.</p>

      {loading && <div className="text-center">Cargando...</div>}

      <div className="grid gap-4">
        {adventures.map(adv => {
          const isAvailable = adv.status === 'available';
          const isActive = adv.status === 'active';
          const isCompleted = adv.status === 'completed'; // Actually backend sets it to completed only after claim? No, wait.
          // Backend sets status to 'active' when started.
          // When claiming, it checks if time passed.
          // So frontend needs to check if time passed to show "Claim" button.
          
          const endTime = new Date(adv.started_at);
          endTime.setSeconds(endTime.getSeconds() + adv.duration);
          const now = new Date();
          const isReadyToClaim = isActive && now >= endTime;
          
          return (
            <div key={adv.id} className="bg-gray-800 p-4 rounded border border-gray-700 flex justify-between items-center">
              <div>
                <div className={`font-bold capitalize ${getDifficultyColor(adv.difficulty)}`}>
                  {adv.difficulty} ({adv.duration / 60} min)
                </div>
                <div className="text-sm text-gray-500">
                  Estado: <span className="capitalize text-white">{adv.status}</span>
                </div>
              </div>

              <div className="flex items-center gap-4">
                {isActive && !isReadyToClaim && (
                  <div className="text-yellow-400 font-mono">
                    <Timer targetDate={endTime} onFinish={() => fetchAdventures()} />
                  </div>
                )}

                {isAvailable && (
                  <button 
                    onClick={() => handleStart(adv.id)}
                    className="btn btn-sm btn-primary"
                  >
                    Comenzar
                  </button>
                )}

                {isReadyToClaim && (
                  <button 
                    onClick={() => handleClaim(adv.id)}
                    className="btn btn-sm btn-success"
                  >
                    Reclamar Recompensa
                  </button>
                )}
                
                {adv.status === 'completed' && (
                    <span className="text-green-500">Completada</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Result Modal */}
      {claimResult && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="bg-gray-800 p-6 rounded-lg max-w-md w-full border border-amber-500">
            <h2 className="text-2xl font-bold text-amber-500 mb-4">¡Aventura Completada!</h2>
            
            <div className="space-y-2 mb-6">
              <div className="flex justify-between">
                <span>Daño recibido:</span>
                <span className="text-red-400">-{claimResult.damage} HP</span>
              </div>
              <div className="flex justify-between">
                <span>Experiencia:</span>
                <span className="text-blue-400">+{claimResult.xp} XP</span>
              </div>
              
              {claimResult.loot ? (
                <div className="mt-4 p-3 bg-gray-700 rounded">
                  <div className="text-sm text-gray-400">Botín encontrado:</div>
                  {claimResult.loot.type === 'item' ? (
                    <div className="font-bold text-purple-400">{claimResult.loot.name} ({claimResult.loot.rarity})</div>
                  ) : (
                    <div className="font-bold text-green-400">
                      {claimResult.loot.amount} {claimResult.loot.resource}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-gray-500 italic mt-2">No encontraste nada de valor.</div>
              )}
            </div>

            <button 
              onClick={() => setClaimResult(null)}
              className="btn btn-primary w-full"
            >
              Continuar
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdventuresView;
