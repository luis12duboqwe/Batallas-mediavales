import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const resourceCostMeta = [
  ['wood', '🪵'],
  ['stone', '🪨'],
  ['iron', '⛓️'],
  ['gold', '🪙'],
];

const AcademyView = () => {
  const { t } = useTranslation();
  const { loadCity } = useCityStore();
  const [city, setCity] = useState(null);
  const [units, setUnits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const loadCatalog = useCallback(async (targetCity) => {
    if (!targetCity?.id || !targetCity?.world_id) return [];
    const { data } = await api.getAvailableUnits(targetCity.id, targetCity.world_id);
    setUnits(data || []);
    return data || [];
  }, []);

  const refresh = useCallback(async () => {
    const data = await loadCity();
    const refreshedCity = data?.city || null;
    setCity(refreshedCity);
    if (refreshedCity) {
      await loadCatalog(refreshedCity);
    }
    return refreshedCity;
  }, [loadCity, loadCatalog]);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((error) => {
        setMessage(error.response?.data?.detail || 'No se pudo cargar la academia');
      })
      .finally(() => setLoading(false));
  }, [refresh]);

  const handleResearch = async (unitType) => {
    if (!city) return;
    setLoading(true);
    setMessage('');
    try {
      await api.researchUnit(city.id, city.world_id, unitType);
      await refresh();
      setMessage(`Investigación de ${t(unitType)} completada`);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error en investigación');
    } finally {
      setLoading(false);
    }
  };

  const formatRequirements = (requirements) =>
    Object.entries(requirements || {}).map(
      ([buildingName, level]) => `${t(buildingName)} Nv. ${level}`
    );

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <h2 className="text-3xl font-bold mb-6 text-amber-500">Academia Militar</h2>

      {message && (
        <div className="glass-panel p-3 mb-4 text-sm text-amber-100">{message}</div>
      )}

      {loading && units.length === 0 && <div className="skeleton h-40 w-full" />}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {units.map((unit) => {
          const missingRequirements = unit.research_requirements_met
            ? []
            : formatRequirements(unit.research_requirements);
          const cost = unit.research_cost || {};
          const visibleCosts = resourceCostMeta.filter(([resource]) => (cost[resource] || 0) > 0);

          return (
            <div
              key={unit.unit_type}
              className={`bg-gray-800 border ${unit.researched ? 'border-green-600' : 'border-gray-600'} p-5 rounded-lg shadow-lg relative overflow-hidden`}
            >
              {unit.researched && (
                <div className="absolute top-0 right-0 bg-green-600 text-white text-xs px-2 py-1 rounded-bl">
                  Investigado
                </div>
              )}

              <h3 className="font-bold text-xl text-amber-100 mb-2">{t(unit.unit_type)}</h3>

              <div className="text-sm text-gray-400 mb-4">
                {visibleCosts.length > 0 ? (
                  <div className="flex gap-2 mb-1 flex-wrap">
                    {visibleCosts.map(([resource, icon]) => (
                      <span key={resource}>{icon} {cost[resource]}</span>
                    ))}
                  </div>
                ) : (
                  <span className="text-green-300">Disponible desde el inicio</span>
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
                  onClick={() => handleResearch(unit.unit_type)}
                  disabled={loading || !unit.can_research}
                  className={`w-full py-2 rounded font-bold transition ${
                    !unit.can_research
                      ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                      : 'bg-amber-600 hover:bg-amber-500 text-white'
                  }`}
                >
                  {!unit.research_requirements_met
                    ? 'Requisitos no cumplidos'
                    : !unit.can_research
                      ? 'Recursos insuficientes'
                      : 'Investigar'}
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
