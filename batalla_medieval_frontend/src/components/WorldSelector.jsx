import { useEffect, useState } from 'react';
import { useWorldStore } from '../store/worldStore';
import { useUserStore } from '../store/userStore';
import { useCityStore } from '../store/cityStore';
import GameIcon from './GameIcon';

const WorldSelector = () => {
  const { worlds, currentWorldId, loadWorlds, setActiveWorld, joinWorld } = useWorldStore();
  const { user } = useUserStore();
  const { loadCity } = useCityStore();
  const [selectedWorld, setSelectedWorld] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) loadWorlds().catch(() => {});
  }, [user, loadWorlds]);

  useEffect(() => {
    if (currentWorldId) setSelectedWorld(currentWorldId);
  }, [currentWorldId]);

  const handleWorldSelect = async (worldId) => {
    if (worldId === currentWorldId) return;
    setLoading(true);
    try {
      await setActiveWorld(worldId);
      await loadCity();
      setSelectedWorld(worldId);
    } catch (error) {
      console.error('Error al cambiar de mundo:', error);
    } finally { setLoading(false); }
  };

  const handleJoinWorld = async (worldId) => {
    setLoading(true);
    try {
      await joinWorld(worldId);
      await loadCity();
    } catch (error) {
      console.error('Error al unirse al mundo:', error);
    } finally { setLoading(false); }
  };

  if (!user) return null;

  return (
    <section className="space-y-4" aria-labelledby="world-selector-heading">
      <div><h2 id="world-selector-heading" className="text-2xl font-bold mb-2">Seleccionar Mundo</h2><p className="text-gray-400 text-sm">Elige o únete a un mundo abierto</p></div>
      {worlds.length === 0 && <div className="card p-6 text-center text-gray-400">No hay mundos disponibles. Contacta con un administrador.</div>}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {worlds.map((world) => {
          const isActive = world.id === currentWorldId;
          return (
            <article key={world.id} data-testid={`world-selector-${world.id}`} className={`card overflow-hidden transition ${isActive ? 'border-2 border-yellow-500 shadow-yellow-500/50' : ''}`} aria-current={isActive ? 'true' : undefined}>
              <button
                type="button"
                className="w-full p-5 text-left hover:bg-white/5 disabled:cursor-default disabled:opacity-100"
                onClick={() => !loading && handleWorldSelect(world.id)}
                disabled={loading || isActive}
                aria-label={isActive ? `${world.name}, mundo activo` : `Seleccionar mundo ${world.name}`}
              >
                <span className="flex items-start justify-between mb-3">
                  <span><span className="text-xl font-bold block">{world.name}</span><span className="text-xs uppercase tracking-wide text-green-400 block" data-testid={`world-status-${world.id}`}>{world.lifecycle_status || 'open'}</span>{isActive && <span className="badge mt-1">Mundo activo</span>}</span>
                  <span className="text-yellow-300"><GameIcon name="map" size={26} /></span>
                </span>
                <span className="space-y-2 text-sm text-gray-300 block"><span className="block"><span className="text-gray-400">Velocidad:</span> {world.speed_modifier}x</span><span className="block"><span className="text-gray-400">Recursos:</span> {world.resource_modifier}x</span><span className="block"><span className="text-gray-400">Tamaño mapa:</span> {world.map_size}x{world.map_size}</span></span>
              </button>
              {!isActive && <div className="px-5 pb-5"><button type="button" onClick={() => handleJoinWorld(world.id)} disabled={loading} className="btn-primary w-full">{loading ? 'Procesando...' : 'Unirse'}</button></div>}
            </article>
          );
        })}
      </div>
    </section>
  );
};

export default WorldSelector;
