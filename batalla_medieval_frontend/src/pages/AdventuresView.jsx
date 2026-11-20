import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/axiosClient';
import Timer from '../components/Timer';
import { useCityStore } from '../store/cityStore';
import useModalAccessibility from '../hooks/useModalAccessibility';
import {
  adventureDeadlineMs,
  applyAdventureResponse,
  canClaimAdventure,
} from '../components/parallel-adventures/adventureState';

const STATUS_LABELS = {
  available: 'Disponible',
  active: 'En curso',
  completed: 'Recompensada',
  failed: 'Finalizada en derrota',
};

const getDifficultyColor = (difficulty) => {
  if (difficulty === 'easy') return 'text-green-400';
  if (difficulty === 'medium') return 'text-yellow-400';
  if (difficulty === 'hard') return 'text-red-400';
  return 'text-gray-400';
};

const errorDetail = (error, fallback) => (
  typeof error?.response?.data?.detail === 'string'
    ? error.response.data.detail
    : fallback
);

const AdventuresView = () => {
  const currentCity = useCityStore((state) => state.currentCity);
  const worldId = currentCity?.world_id;
  const [adventures, setAdventures] = useState([]);
  const [loadedWorldId, setLoadedWorldId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pendingAction, setPendingAction] = useState(null);
  const [claimResult, setClaimResult] = useState(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const activeWorldRef = useRef(null);
  const requestGenerationRef = useRef(0);
  const activeActionRef = useRef(null);
  const resultDialogRef = useModalAccessibility(Boolean(claimResult), () => setClaimResult(null));

  const fetchAdventures = useCallback(async (targetWorld, { clearError = true } = {}) => {
    if (!targetWorld || activeWorldRef.current !== targetWorld) return null;
    const generation = ++requestGenerationRef.current;
    setLoading(true);
    if (clearError) setError('');

    try {
      const response = await api.getAdventures(targetWorld);
      if (activeWorldRef.current !== targetWorld || generation !== requestGenerationRef.current) return null;
      const rows = Array.isArray(response.data) ? response.data : [];
      setAdventures(rows);
      setLoadedWorldId(targetWorld);
      setNowMs(Date.now());
      return rows;
    } catch (err) {
      if (activeWorldRef.current === targetWorld && generation === requestGenerationRef.current) {
        setError(errorDetail(err, 'No se pudieron cargar las aventuras. Puedes reintentar.'));
      }
      return null;
    } finally {
      if (activeWorldRef.current === targetWorld && generation === requestGenerationRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    activeWorldRef.current = worldId;
    activeActionRef.current = null;
    setPendingAction(null);
    setClaimResult(null);
    setAdventures([]);
    setLoadedWorldId(null);
    setError('');
    if (worldId) {
      void fetchAdventures(worldId);
    } else {
      setLoading(false);
    }

    return () => {
      if (activeWorldRef.current === worldId) activeWorldRef.current = null;
      requestGenerationRef.current += 1;
    };
  }, [worldId, fetchAdventures]);

  // Keep BM-0085's deadline-based update; also recover when a background tab
  // becomes visible or the device clock changes during suspension.
  useEffect(() => {
    const updateClock = () => setNowMs(Date.now());
    const onVisibility = () => {
      if (document.visibilityState === 'visible') updateClock();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('focus', updateClock);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', updateClock);
    };
  }, []);

  useEffect(() => {
    const visible = loadedWorldId === worldId ? adventures : [];
    const upcoming = visible
      .filter((adventure) => adventure.status === 'active')
      .map(adventureDeadlineMs)
      .filter((deadline) => deadline !== null && deadline > nowMs);
    if (upcoming.length === 0) return undefined;
    const nearest = Math.min(...upcoming);
    const timer = setTimeout(() => setNowMs(Date.now()), Math.max(0, nearest - Date.now() + 50));
    return () => clearTimeout(timer);
  }, [adventures, loadedWorldId, nowMs, worldId]);

  const handleAction = async (id, action) => {
    const targetWorld = worldId;
    if (!targetWorld || loadedWorldId !== targetWorld || loading || activeActionRef.current) return;
    const task = { id, action, worldId: targetWorld };
    activeActionRef.current = task;
    setPendingAction(task);
    setError('');
    // A prior GET must not overwrite a newly confirmed server mutation.
    requestGenerationRef.current += 1;
    const isCurrent = () => activeWorldRef.current === targetWorld && activeActionRef.current === task;

    try {
      const response = action === 'start'
        ? await api.startAdventure(id, targetWorld)
        : await api.claimAdventure(id, targetWorld);
      if (!isCurrent()) return;
      setAdventures((rows) => applyAdventureResponse(rows, id, action, response.data));
      if (action === 'claim' && response.data) setClaimResult(response.data);
      setNowMs(Date.now());
      // A failed refresh must not roll back a mutation acknowledged by the API.
      await fetchAdventures(targetWorld);
    } catch (err) {
      if (!isCurrent()) return;
      // A disconnected POST might have committed. Read the server before
      // offering a retry rather than automatically resending a mutation.
      const rows = await fetchAdventures(targetWorld, { clearError: false });
      if (!isCurrent()) return;
      const synced = rows?.find((adventure) => String(adventure.id) === String(id));
      const alreadyApplied = action === 'start'
        ? synced?.status === 'active'
        : ['completed', 'failed'].includes(synced?.status) && Boolean(synced.result);
      if (alreadyApplied) {
        if (action === 'claim') setClaimResult(synced.result);
        setError('');
      } else {
        const fallback = action === 'start'
          ? 'No se pudo confirmar el inicio. Actualiza antes de volver a intentarlo.'
          : 'No se pudo confirmar la recompensa. Actualiza antes de volver a intentarlo.';
        setError(rows === null ? fallback : errorDetail(err, fallback));
      }
    } finally {
      if (isCurrent()) {
        activeActionRef.current = null;
        setPendingAction(null);
      }
    }
  };

  if (!worldId) return <div className="p-6" role="status">Cargando mundo...</div>;

  const visibleAdventures = loadedWorldId === worldId ? adventures : [];
  const controlsBusy = loading || Boolean(pendingAction) || loadedWorldId !== worldId;

  return (
    <div className="p-6 max-w-4xl mx-auto" data-testid="adventures-view">
      <h1 className="text-3xl font-bold mb-2 text-amber-500">Aventuras</h1>
      <p className="text-gray-400 mb-6">Envía a tu héroe a expediciones temporizadas para obtener experiencia, recursos u objetos.</p>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div role="status" aria-live="polite" data-testid="adventure-action-status">
          {pendingAction
            ? (pendingAction.action === 'claim' ? 'Confirmando recompensa...' : 'Iniciando aventura...')
            : (loading ? 'Actualizando aventuras...' : '')}
        </div>
        <button
          type="button"
          className="btn btn-sm btn-outline"
          disabled={loading || Boolean(pendingAction)}
          onClick={() => void fetchAdventures(worldId)}
          data-testid="adventure-refresh"
        >
          Actualizar aventuras
        </button>
      </div>
      {error && <div role="alert" className="alert alert-error mb-4">{error}</div>}
      {!loading && loadedWorldId === worldId && visibleAdventures.length === 0 && (
        <p className="text-gray-400" role="status">No hay aventuras disponibles por ahora.</p>
      )}

      <div className="grid gap-4">
        {visibleAdventures.map((adv) => {
          const isAvailable = adv.status === 'available';
          const isActive = adv.status === 'active';
          const deadlineMs = adventureDeadlineMs(adv);
          const endTime = deadlineMs === null ? null : new Date(deadlineMs);
          const isReadyToClaim = canClaimAdventure(adv, nowMs);
          const isPending = pendingAction?.id === adv.id;
          const isTerminal = ['completed', 'failed'].includes(adv.status);

          return (
            <article
              key={adv.id}
              className="bg-gray-800 p-4 rounded border border-gray-700 flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4"
              data-testid={`adventure-${adv.id}`}
              aria-busy={isPending}
            >
              <div>
                <div className={`font-bold capitalize ${getDifficultyColor(adv.difficulty)}`}>
                  {adv.difficulty} ({Math.round(adv.duration / 60)} min)
                </div>
                <div className="text-sm text-gray-500">
                  Estado: <span className="text-white">{STATUS_LABELS[adv.status] || adv.status}</span>
                </div>
                <div className="text-xs text-gray-500 mt-1">Reglas: {adv.rules_version || 'pendiente'}</div>
                {adv.outcome_seed && (
                  <div className="text-xs text-gray-600 break-all" data-testid="adventure-seed">
                    Seed: {adv.outcome_seed}
                  </div>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-4">
                {isActive && !isReadyToClaim && endTime && (
                  <div className="text-yellow-400 font-mono"><Timer endTime={endTime} /></div>
                )}
                {isActive && deadlineMs === null && (
                  <span className="text-yellow-400 text-sm">Horario no disponible; actualiza las aventuras.</span>
                )}
                {isAvailable && (
                  <button
                    type="button"
                    onClick={() => void handleAction(adv.id, 'start')}
                    disabled={controlsBusy}
                    className="btn btn-sm btn-primary"
                    data-testid={`adventure-start-${adv.id}`}
                  >
                    Comenzar
                  </button>
                )}
                {isReadyToClaim && (
                  <button
                    type="button"
                    onClick={() => void handleAction(adv.id, 'claim')}
                    disabled={controlsBusy}
                    className="btn btn-sm btn-success"
                    data-testid={`adventure-claim-${adv.id}`}
                  >
                    Reclamar recompensa
                  </button>
                )}
                {isTerminal && (
                  <span className={adv.status === 'completed' ? 'text-green-500' : 'text-red-500'}>
                    {adv.status === 'completed' ? 'Completada' : 'Fallida'}
                  </span>
                )}
                {isTerminal && adv.result && (
                  <button
                    type="button"
                    className="btn btn-sm btn-outline"
                    onClick={() => setClaimResult(adv.result)}
                    data-testid={`adventure-result-${adv.id}`}
                  >
                    Ver resultado
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {claimResult && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" data-testid="adventure-result">
          <div
            ref={resultDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="adventure-result-title"
            tabIndex={-1}
            className="bg-gray-800 p-6 rounded-lg max-w-md w-full border border-amber-500"
          >
            <h2 id="adventure-result-title" className="text-2xl font-bold text-amber-500 mb-4">
              {claimResult.status === 'dead' ? 'La aventura terminó en derrota' : '¡Aventura completada!'}
            </h2>
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
              <div className="pt-3 text-xs text-gray-500">
                Reglas: <span data-testid="adventure-result-version">{claimResult.rules_version}</span>
              </div>
              <div className="text-xs text-gray-600 break-all">
                Seed: <span data-testid="adventure-result-seed">{claimResult.seed}</span>
              </div>
            </div>
            <button type="button" onClick={() => setClaimResult(null)} className="btn btn-primary w-full">Continuar</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdventuresView;
