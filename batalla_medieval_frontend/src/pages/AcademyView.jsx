import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/axiosClient';
import { researchApi } from '../api/researchApi';
import Timer from '../components/Timer';
import { useCityStore } from '../store/cityStore';

const resourceCostMeta = [
  ['wood', '🪵'],
  ['stone', '🪨'],
  ['iron', '⛓️'],
  ['gold', '🪙'],
];

const formatSeconds = (seconds) => {
  const total = Number(seconds || 0);
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
};

const AcademyView = () => {
  const { t } = useTranslation();
  const { loadCity } = useCityStore();
  const [city, setCity] = useState(null);
  const [units, setUnits] = useState([]);
  const [activeQueue, setActiveQueue] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const loadCatalogAndQueue = useCallback(async (targetCity) => {
    if (!targetCity?.id || !targetCity?.world_id) return;
    const [catalogResponse, queueResponse] = await Promise.all([
      api.getAvailableUnits(targetCity.id, targetCity.world_id),
      researchApi.getQueue(targetCity.world_id),
    ]);
    setUnits(catalogResponse.data || []);
    const queue = (queueResponse.data || []).find(
      (entry) => entry.city_id === targetCity.id,
    ) || null;
    setActiveQueue(queue);
  }, []);

  const refresh = useCallback(async () => {
    const data = await loadCity();
    const refreshedCity = data?.city || null;
    setCity(refreshedCity);
    if (refreshedCity) {
      await loadCatalogAndQueue(refreshedCity);
    } else {
      setUnits([]);
      setActiveQueue(null);
    }
    return refreshedCity;
  }, [loadCity, loadCatalogAndQueue]);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    refresh()
      .catch((error) => {
        if (mounted) {
          setMessage(error.response?.data?.detail || 'No se pudo cargar la academia');
        }
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    const interval = setInterval(() => {
      refresh().catch(() => {});
    }, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [refresh]);

  const handleResearch = async (unitType) => {
    if (!city || activeQueue) return;
    setLoading(true);
    setMessage('');
    try {
      await researchApi.queue(city.id, city.world_id, unitType);
      await refresh();
      setMessage(`Investigación de ${t(unitType)} iniciada`);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error al iniciar la investigación');
    } finally {
      setLoading(false);
    }
  };

  const handleCancelResearch = async () => {
    if (!activeQueue) return;
    setLoading(true);
    setMessage('');
    try {
      await researchApi.cancel(activeQueue.id);
      await refresh();
      setMessage('Investigación cancelada; se aplicó el reembolso correspondiente.');
    } catch (error) {
      setMessage(error.response?.data?.detail || 'No se pudo cancelar la investigación');
    } finally {
      setLoading(false);
    }
  };

  const formatRequirements = (requirements) =>
    Object.entries(requirements || {}).map(
      ([buildingName, level]) => `${t(buildingName)} Nv. ${level}`,
    );

  return (
    <div className="p-4 max-w-6xl mx-auto" data-testid="academy-view">
      <h2 className="text-3xl font-bold mb-2 text-amber-500">Academia Militar</h2>
      <p className="text-sm text-gray-400 mb-6">
        Investiga una tecnología a la vez. El desbloqueo se aplica cuando termina el temporizador.
      </p>

      {message && (
        <div className="glass-panel p-3 mb-4 text-sm text-amber-100" data-testid="academy-message">
          {message}
        </div>
      )}

      {activeQueue && (
        <div
          className="glass-panel p-4 mb-6 border border-amber-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
          data-testid="research-active-queue"
        >
          <div>
            <div className="text-xs uppercase tracking-wide text-gray-400">Investigación activa</div>
            <div className="font-bold text-amber-100" data-testid="research-active-tech">
              {t(activeQueue.tech_name)}
            </div>
            <div className="text-sm text-gray-300 mt-1">
              Tiempo restante: <Timer endTime={activeQueue.finish_time} />
            </div>
          </div>
          <button
            type="button"
            onClick={handleCancelResearch}
            disabled={loading}
            className="px-4 py-2 rounded bg-red-900/70 hover:bg-red-800 text-red-100 disabled:opacity-50"
            data-testid="cancel-research"
          >
            Cancelar investigación
          </button>
        </div>
      )}

      {loading && units.length === 0 && <div className="skeleton h-40 w-full" />}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {units.map((unit) => {
          const missingRequirements = unit.research_requirements_met
            ? []
            : formatRequirements(unit.research_requirements);
          const cost = unit.research_cost || {};
          const visibleCosts = resourceCostMeta.filter(
            ([resource]) => Number(cost[resource] || 0) > 0,
          );
          const queuedForUnit = activeQueue?.tech_name === unit.unit_type || unit.research_queued;
          const queueOccupied = Boolean(activeQueue) && !queuedForUnit;

          let actionLabel = 'Investigar';
          if (!unit.research_requirements_met) actionLabel = 'Requisitos no cumplidos';
          else if (queuedForUnit) actionLabel = 'Investigando';
          else if (queueOccupied) actionLabel = 'Cola de investigación ocupada';
          else if (!unit.can_research) actionLabel = 'Recursos insuficientes';

          return (
            <div
              key={unit.unit_type}
              data-testid={`research-card-${unit.unit_type}`}
              className={`bg-gray-800 border ${unit.researched ? 'border-green-600' : queuedForUnit ? 'border-amber-500' : 'border-gray-600'} p-5 rounded-lg shadow-lg relative overflow-hidden`}
            >
              {unit.researched && (
                <div className="absolute top-0 right-0 bg-green-600 text-white text-xs px-2 py-1 rounded-bl">
                  Investigado
                </div>
              )}

              <h3 className="font-bold text-xl text-amber-100 mb-2">{t(unit.unit_type)}</h3>

              <div className="text-sm text-gray-400 mb-4 space-y-2">
                {visibleCosts.length > 0 ? (
                  <div className="flex gap-2 flex-wrap">
                    {visibleCosts.map(([resource, icon]) => (
                      <span key={resource}>{icon} {cost[resource]}</span>
                    ))}
                  </div>
                ) : (
                  <span className="text-green-300">Disponible desde el inicio</span>
                )}
                {unit.research_time_seconds > 0 && (
                  <div>⏱️ {formatSeconds(unit.research_time_seconds)}</div>
                )}
              </div>

              {!unit.researched && missingRequirements.length > 0 && (
                <div className="mb-4 bg-red-900/30 p-2 rounded border border-red-900/50">
                  <div className="text-xs text-red-300 font-bold mb-1">Requisitos:</div>
                  <ul className="list-disc list-inside text-xs text-red-200">
                    {missingRequirements.map((requirement) => (
                      <li key={requirement}>{requirement}</li>
                    ))}
                  </ul>
                </div>
              )}

              {unit.researched ? (
                <button
                  disabled
                  className="w-full bg-green-800/50 text-green-200 py-2 rounded cursor-default border border-green-700"
                >
                  Tecnología Dominada
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => handleResearch(unit.unit_type)}
                  disabled={loading || !unit.can_research || Boolean(activeQueue)}
                  data-testid={`research-action-${unit.unit_type}`}
                  className={`w-full py-2 rounded font-bold transition ${
                    !unit.can_research || activeQueue
                      ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                      : 'bg-amber-600 hover:bg-amber-500 text-white'
                  }`}
                >
                  {actionLabel}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AcademyView;
