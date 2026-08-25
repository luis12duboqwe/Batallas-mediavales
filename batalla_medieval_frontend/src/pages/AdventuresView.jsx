import { useCallback, useEffect, useState } from 'react';
import heroApi from '../api/heroApi';
import Timer from '../components/Timer';
import { useCityStore } from '../store/cityStore';

const LABELS = { easy: 'Fácil', medium: 'Media', hard: 'Difícil' };
const CLASSES = { easy: 'text-green-400', medium: 'text-yellow-300', hard: 'text-red-400' };

const errorText = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : detail?.message || fallback;
};

const durationText = (seconds) => {
  const value = Number(seconds || 0);
  if (value < 60) return `${value} s`;
  if (value < 3600) return `${Math.round(value / 60)} min`;
  return `${(value / 3600).toFixed(value % 3600 ? 1 : 0)} h`;
};

const AdventuresView = () => {
  const { currentCity, loadCity } = useCityStore();
  const worldId = currentCity?.world_id ?? null;
  const [adventures, setAdventures] = useState([]);
  const [rules, setRules] = useState(null);
  const [claimResult, setClaimResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    if (!worldId) return;
    setLoading(true);
    try {
      const [adventureResponse, balanceResponse] = await Promise.all([
        heroApi.getAdventures(worldId),
        heroApi.getRules(),
      ]);
      setAdventures(adventureResponse.data || []);
      setRules(balanceResponse.data?.hero_package || null);
      setError('');
    } catch (requestError) {
      setError(errorText(requestError, 'No se pudieron cargar las aventuras.'));
    } finally {
      setLoading(false);
    }
  }, [worldId]);

  useEffect(() => { refresh(); }, [refresh]);

  const start = async (id) => {
    setBusyId(id);
    try {
      await heroApi.startAdventure(worldId, id);
      await refresh();
    } catch (requestError) {
      setError(errorText(requestError, 'No se pudo iniciar la aventura.'));
    } finally {
      setBusyId(null);
    }
  };

  const claim = async (id) => {
    setBusyId(id);
    try {
      const response = await heroApi.claimAdventure(worldId, id);
      setClaimResult(response.data);
      await Promise.all([refresh(), loadCity()]);
    } catch (requestError) {
      setError(errorText(requestError, 'No se pudo reclamar la aventura.'));
    } finally {
      setBusyId(null);
    }
  };

  if (!worldId) return <div role="status">Cargando ciudad activa...</div>;

  return (
    <div className="p-3 sm:p-6 max-w-5xl mx-auto pb-24" data-testid="adventure-package" data-rules-version={rules?.rules_version || ''}>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3 mb-6">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-amber-300">Héroe</p>
          <h1 className="text-3xl font-bold text-amber-500">Aventuras</h1>
          <p className="text-gray-400 mt-2">Misiones temporizadas con resultado determinado por el servidor.</p>
        </div>
        {rules && <div className="text-xs font-mono text-gray-500" data-testid="adventure-rules-version">Reglas {rules.rules_version}</div>}
      </div>

      {rules && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6" data-testid="adventure-rules">
          <div className="card bg-black/40 p-3"><span className="text-xs text-gray-500">Lote</span><strong>{rules.adventures_per_batch} aventuras</strong></div>
          <div className="card bg-black/40 p-3"><span className="text-xs text-gray-500">Objeto</span><strong>{Math.round((rules.loot?.item_chance || 0) * 100)}%</strong></div>
          <div className="card bg-black/40 p-3"><span className="text-xs text-gray-500">Recurso</span><strong>{Math.round((rules.loot?.resource_chance || 0) * 100)}%</strong></div>
        </div>
      )}

      {error && <div role="alert" className="alert alert-error mb-4">{error}</div>}
      {loading && <div role="status" className="py-6 text-center">Cargando aventuras...</div>}

      <div className="space-y-3">
        {adventures.map((adventure) => {
          const active = adventure.status === 'active';
          const available = adventure.status === 'available';
          const endTime = active && adventure.started_at
            ? new Date(new Date(adventure.started_at).getTime() + Number(adventure.duration) * 1000)
            : null;
          const ready = Boolean(endTime && Date.now() >= endTime.getTime());
          return (
            <article key={adventure.id} className="card bg-black/40 border border-amber-900/30 p-4" data-testid="adventure-row" data-adventure-id={adventure.id} data-adventure-seed={adventure.seed}>
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div>
                  <div className={`font-bold text-lg ${CLASSES[adventure.difficulty] || ''}`}>{LABELS[adventure.difficulty] || adventure.difficulty}</div>
                  <div className="text-sm text-gray-400">Duración: {durationText(adventure.duration)}</div>
                  <div className="text-xs text-gray-500">Estado: {available ? 'Disponible' : active ? 'En curso' : adventure.status === 'completed' ? 'Completada' : 'Fallida'}</div>
                </div>
                <div className="flex items-center gap-3">
                  {active && !ready && endTime && <Timer targetDate={endTime} onFinish={refresh} />}
                  {available && <button type="button" className="btn btn-sm btn-primary" onClick={() => start(adventure.id)} disabled={busyId !== null}>Comenzar</button>}
                  {active && ready && <button type="button" className="btn btn-sm btn-success" data-testid="adventure-claim" onClick={() => claim(adventure.id)} disabled={busyId !== null}>Reclamar</button>}
                  {['completed', 'failed'].includes(adventure.status) && <span className="badge">{adventure.status === 'completed' ? 'Resuelta' : 'Fallida'}</span>}
                </div>
              </div>
              <details className="mt-3 text-xs text-gray-500"><summary>Auditoría</summary><div className="font-mono break-all mt-1" data-testid="adventure-seed">{adventure.seed}</div><div className="font-mono">{adventure.rules_version}</div></details>
            </article>
          );
        })}
      </div>

      {claimResult && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" data-testid="adventure-claim-result">
          <div className="bg-gray-900 p-6 rounded-xl max-w-md w-full border border-amber-500">
            <h2 className="text-2xl font-bold text-amber-400 mb-4">Resultado de aventura</h2>
            <div className="flex justify-between"><span>Daño</span><strong>-{claimResult.damage} HP</strong></div>
            <div className="flex justify-between"><span>Experiencia</span><strong>+{claimResult.xp} XP</strong></div>
            {claimResult.loot?.type === 'item' && <div className="mt-3 p-3 bg-black/40 rounded">Objeto: <strong>{claimResult.loot.name}</strong></div>}
            {claimResult.loot?.type === 'resource' && <div className="mt-3 p-3 bg-black/40 rounded">Recursos: <strong>{claimResult.loot.amount} {claimResult.loot.resource}</strong>{claimResult.loot.storage_capped && <div className="text-xs text-yellow-300">Limitado por almacén.</div>}</div>}
            {!claimResult.loot && <div className="mt-3 text-gray-500">Sin botín adicional.</div>}
            <div className="text-xs text-gray-500 font-mono break-all mt-4" data-testid="claim-audit-seed">{claimResult.seed}</div>
            <div className="text-xs text-gray-500 font-mono">{claimResult.rules_version}</div>
            <button type="button" className="btn btn-primary w-full mt-5" onClick={() => setClaimResult(null)}>Continuar</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdventuresView;
