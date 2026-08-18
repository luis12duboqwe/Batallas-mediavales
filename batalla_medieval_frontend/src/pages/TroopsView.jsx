import { useCallback, useEffect, useState } from 'react';
import TroopCard from '../components/TroopCard';
import Timer from '../components/Timer';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const TroopsView = () => {
  const { queues, train, loadCity, cancelTroop, currentCity } = useCityStore();
  const [units, setUnits] = useState([]);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [message, setMessage] = useState('');

  const loadCatalog = useCallback(async (city = currentCity) => {
    if (!city?.id || !city?.world_id) return [];
    setLoadingCatalog(true);
    try {
      const { data } = await api.getAvailableUnits(city.id, city.world_id);
      setUnits(data || []);
      return data || [];
    } finally {
      setLoadingCatalog(false);
    }
  }, [currentCity]);

  useEffect(() => {
    const bootstrap = async () => {
      const data = await loadCity();
      if (data?.city) {
        await loadCatalog(data.city);
      }
    };
    bootstrap().catch((error) => {
      setMessage(error.response?.data?.detail || 'No se pudo cargar el catálogo de tropas');
    });
  }, [loadCity, loadCatalog]);

  const handleTrain = async ({ troopType, amount }) => {
    setMessage('');
    try {
      await train({ troopType, amount });
      const refreshed = await loadCity();
      if (refreshed?.city) {
        await loadCatalog(refreshed.city);
      }
      setMessage(`${amount}x ${troopType} agregado a la cola`);
    } catch (error) {
      setMessage(error.response?.data?.detail || 'No se pudo iniciar el entrenamiento');
      throw error;
    }
  };

  const handleCancel = async (queueId) => {
    setMessage('');
    try {
      await cancelTroop(queueId);
      const refreshed = await loadCity();
      if (refreshed?.city) {
        await loadCatalog(refreshed.city);
      }
    } catch (error) {
      setMessage(error.response?.data?.detail || 'No se pudo cancelar el entrenamiento');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Tropas</h1>
          <p className="text-gray-400">Entrena y organiza tus ejércitos con costos definidos por el servidor</p>
        </div>
        <span className="badge">Panel táctico</span>
      </div>

      {message && (
        <div className="glass-panel p-3 text-sm text-amber-100">{message}</div>
      )}

      <div className="grid lg:grid-cols-[2fr,1fr] gap-6">
        <div className="grid md:grid-cols-2 gap-4">
          {loadingCatalog && units.length === 0 && (
            <div className="skeleton h-40 w-full md:col-span-2" />
          )}
          {!loadingCatalog && units.length === 0 && (
            <p className="text-gray-400 md:col-span-2">No hay unidades disponibles.</p>
          )}
          {units.map((unit) => (
            <TroopCard
              key={unit.unit_type}
              troop={unit}
              onTrain={handleTrain}
            />
          ))}
        </div>

        <div className="card p-5 space-y-4 sticky top-32 h-fit">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl">Cola de entrenamiento</h2>
              <p className="text-gray-400 text-sm">Revisa los tiempos en vivo</p>
            </div>
            <span className="badge">Tiempo real</span>
          </div>
          <div className="space-y-3">
            {queues.troops?.length === 0 && <p className="text-gray-400">Sin entrenamientos activos</p>}
            {queues.troops?.map((q) => (
              <div key={q.id} className="glass-panel p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-yellow-200">{q.amount}x {q.troop_type || q.unit}</p>
                  <p className="text-xs text-gray-400">Entrenamiento en curso</p>
                </div>
                <div className="flex items-center gap-2">
                  <Timer endTime={q.finish_time || q.finishAt} />
                  <button
                    onClick={() => handleCancel(q.id)}
                    className="text-red-400 hover:text-red-300 text-xs underline"
                  >
                    X
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default TroopsView;
