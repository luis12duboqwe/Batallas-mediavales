import { useEffect, useState } from 'react';
import { api } from '../api/axiosClient';
import Timer from '../components/Timer';
import { useCityStore } from '../store/cityStore';

const AdventuresView = () => {
  const { currentCity } = useCityStore();
  const worldId = currentCity?.world_id;
  const [adventures, setAdventures] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [claimResult, setClaimResult] = useState(null);

  const fetchAdventures = async () => {
    if (!worldId) return;
    setLoading(true);
    setError('');
    try {
      const res = await api.getAdventures(worldId);
      setAdventures(res.data || []);
    } catch (err) {
      console.error('Failed to load adventures', err);
      setError(err.response?.data?.detail || 'No se pudieron cargar las aventuras.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAdventures();
  }, [worldId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleStart = async (id) => {
    try {
      await api.startAdventure(id, worldId);
      await fetchAdventures();
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo iniciar la aventura.');
    }
  };

  const handleClaim = async (id) => {
    try {
      const res = await api.claimAdventure(id, worldId);
      setClaimResult(res.data);
      await fetchAdventures();
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo reclamar la aventura.');
    }
  };

  const getDifficultyColor = (difficulty) => {
    if (difficulty === 'easy') return 'text-green-400';
    if (difficulty === 'medium') return 'text-yellow-400';
    if (difficulty === 'hard') return 'text-red-400';
    return 'text-gray-400';
  };

  if (!worldId) return <div className="p-6">Cargando mundo...</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto" data-testid="adventures-view">
      <h1 className="text-3xl font-bold mb-2 text-amber-500">Aventuras</h1>
      <p className="text-gray-400 mb-8">Envía a tu héroe a expediciones temporizadas para obtener experiencia, recursos u objetos.</p>
      {error && <div role="alert" className="alert alert-error mb-4">{error}</div>}
      {loading && <div className="text-center">Cargando...</div>}

      <div className="grid gap-4">
        {adventures.map((adv) => {
          const isAvailable = adv.status === 'available';
          const isActive = adv.status === 'active';
          const endTime = adv.started_at ? new Date(adv.started_at) : null;
          if (endTime) endTime.setSeconds(endTime.getSeconds() + adv.duration);
          const isReadyToClaim = isActive && endTime && new Date() >= endTime;

          return (
            <div key={adv.id} className="bg-gray-800 p-4 rounded border border-gray-700 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4" data-testid={`adventure-${adv.id}`}>
              <div>
                <div className={`font-bold capitalize ${getDifficultyColor(adv.difficulty)}`}>
                  {adv.difficulty} ({Math.round(adv.duration / 60)} min)
                </div>
                <div className="text-sm text-gray-500">Estado: <span className="capitalize text-white">{adv.status}</span></div>
                <div className="text-xs text-gray-500 mt-1">Reglas: {adv.rules_version || 'pendiente'}</div>
                {adv.outcome_seed && <div className="text-xs text-gray-600 break-all" data-testid="adventure-seed">Seed: {adv.outcome_seed}</div>}
              </div>

              <div className="flex items-center gap-4">
                {isActive && !isReadyToClaim && endTime && (
                  <div className="text-yellow-400 font-mono"><Timer targetDate={endTime} onFinish={fetchAdventures} /></div>
                )}
                {isAvailable && <button type="button" onClick={() => handleStart(adv.id)} className="btn btn-sm btn-primary" data-testid={`adventure-start-${adv.id}`}>Comenzar</button>}
                {isReadyToClaim && <button type="button" onClick={() => handleClaim(adv.id)} className="btn btn-sm btn-success" data-testid={`adventure-claim-${adv.id}`}>Reclamar recompensa</button>}
                {adv.status === 'completed' && <span className="text-green-500">Completada</span>}
                {adv.status === 'failed' && <span className="text-red-500">Fallida</span>}
              </div>
            </div>
          );
        })}
      </div>

      {claimResult && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50" data-testid="adventure-result">
          <div className="bg-gray-800 p-6 rounded-lg max-w-md w-full border border-amber-500">
            <h2 className="text-2xl font-bold text-amber-500 mb-4">{claimResult.status === 'dead' ? 'La aventura terminó en derrota' : '¡Aventura completada!'}</h2>
            <div className="space-y-2 mb-6">
              <div className="flex justify-between"><span>Daño recibido:</span><span className="text-red-400">-{claimResult.damage} HP</span></div>
              <div className="flex justify-between"><span>Experiencia:</span><span className="text-blue-400">+{claimResult.xp} XP</span></div>
              {claimResult.loot ? (
                <div className="mt-4 p-3 bg-gray-700 rounded">
                  <div className="text-sm text-gray-400">Botín encontrado:</div>
                  {claimResult.loot.type === 'item'
                    ? <div className="font-bold text-purple-400">{claimResult.loot.name} ({claimResult.loot.rarity})</div>
                    : <div className="font-bold text-green-400">{claimResult.loot.amount} {claimResult.loot.resource}</div>}
                </div>
              ) : <div className="text-gray-500 italic mt-2">No encontraste nada de valor.</div>}
              <div className="pt-3 text-xs text-gray-500">Reglas: <span data-testid="adventure-result-version">{claimResult.rules_version}</span></div>
              <div className="text-xs text-gray-600 break-all">Seed: <span data-testid="adventure-result-seed">{claimResult.seed}</span></div>
            </div>
            <button type="button" onClick={() => setClaimResult(null)} className="btn btn-primary w-full">Continuar</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdventuresView;
