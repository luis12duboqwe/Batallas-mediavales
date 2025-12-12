import { useEffect, useState } from 'react';
import { useWorldStore } from '../store/worldStore';
import { useUserStore } from '../store/userStore';
import { useCityStore } from '../store/cityStore';

const WorldSelector = () => {
  const { worlds, currentWorldId, loadWorlds, setActiveWorld, joinWorld } = useWorldStore();
  const { user } = useUserStore();
  const { loadCity } = useCityStore();
  const [selectedWorld, setSelectedWorld] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) {
      loadWorlds().catch(() => {});
    }
  }, [user, loadWorlds]);

  useEffect(() => {
    if (currentWorldId) {
      setSelectedWorld(currentWorldId);
    }
  }, [currentWorldId]);

  const handleWorldSelect = async (worldId) => {
    if (worldId === currentWorldId) return;
    setLoading(true);
    try {
      await setActiveWorld(worldId);
      await loadCity();
    } catch (error) {
      console.error('Error al cambiar de mundo:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleJoinWorld = async (worldId) => {
    setLoading(true);
    try {
      await joinWorld(worldId);
      await loadCity();
    } catch (error) {
      console.error('Error al unirse al mundo:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!user) return null;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold mb-2">Seleccionar Mundo</h2>
        <p className="text-gray-400 text-sm">Elige o únete a un mundo activo</p>
      </div>

      {worlds.length === 0 && (
        <div className="card p-6 text-center text-gray-400">
          No hay mundos disponibles. Contacta con un administrador.
        </div>
      )}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {worlds.map((world) => {
          const isActive = world.id === currentWorldId;
          return (
            <div
              key={world.id}
              className={`card p-5 cursor-pointer transition hover:scale-105 ${
                isActive ? 'border-2 border-yellow-500 shadow-yellow-500/50' : ''
              }`}
              onClick={() => !loading && handleWorldSelect(world.id)}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-xl font-bold">{world.name}</h3>
                  {isActive && <span className="badge mt-1">Mundo activo</span>}
                </div>
                <div className="text-2xl">🌍</div>
              </div>

              <div className="space-y-2 text-sm text-gray-300">
                <p>
                  <span className="text-gray-400">Velocidad:</span> {world.speed_modifier}x
                </p>
                <p>
                  <span className="text-gray-400">Recursos:</span> {world.resource_modifier}x
                </p>
                <p>
                  <span className="text-gray-400">Tamaño mapa:</span> {world.map_size}x{world.map_size}
                </p>
              </div>

              {!isActive && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleJoinWorld(world.id);
                  }}
                  disabled={loading}
                  className="btn-primary w-full mt-4"
                >
                  {loading ? 'Procesando...' : 'Unirse'}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default WorldSelector;
