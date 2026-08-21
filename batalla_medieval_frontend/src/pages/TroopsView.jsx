import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import TroopCard from '../components/TroopCard';
import Timer from '../components/Timer';
import { api } from '../api/axiosClient';
import { useCityStore } from '../store/cityStore';

const TroopsView = () => {
  const { t } = useTranslation();
  const { queues, train, loadCity, cancelTroop } = useCityStore();
  const [units, setUnits] = useState([]);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [message, setMessage] = useState('');
  const [messageKind, setMessageKind] = useState('status');
  const [busyQueueId, setBusyQueueId] = useState(null);

  const loadCatalog = useCallback(async (city) => {
    if (!city?.id || !city?.world_id) return [];
    setLoadingCatalog(true);
    try {
      const { data } = await api.getAvailableUnits(city.id, city.world_id);
      setUnits(data || []);
      return data || [];
    } finally {
      setLoadingCatalog(false);
    }
  }, []);

  useEffect(() => {
    const bootstrap = async () => {
      const data = await loadCity();
      if (data?.city) await loadCatalog(data.city);
    };
    bootstrap().catch((error) => {
      setMessageKind('error');
      setMessage(error.response?.data?.detail || 'No se pudo cargar el catálogo de tropas.');
    });
  }, [loadCity, loadCatalog]);

  const handleTrain = async ({ troopType, amount }) => {
    setMessage('');
    try {
      await train({ troopType, amount });
      const refreshed = await loadCity();
      if (refreshed?.city) await loadCatalog(refreshed.city);
      setMessageKind('status');
      setMessage(`${amount}x ${t(troopType)} agregado a la cola.`);
    } catch (error) {
      setMessageKind('error');
      setMessage(error.response?.data?.detail || 'No se pudo iniciar el entrenamiento.');
    }
  };

  const handleCancel = async (queueId) => {
    setBusyQueueId(queueId);
    setMessage('');
    try {
      await cancelTroop(queueId);
      const refreshed = await loadCity();
      if (refreshed?.city) await loadCatalog(refreshed.city);
      setMessageKind('status');
      setMessage('Entrenamiento cancelado y recursos actualizados.');
    } catch (error) {
      setMessageKind('error');
      setMessage(error.response?.data?.detail || 'No se pudo cancelar el entrenamiento.');
    } finally {
      setBusyQueueId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl">Tropas</h1>
          <p className="text-gray-400">Entrena y organiza tus ejércitos con costos definidos por el servidor</p>
        </div>
        <span className="badge w-fit">Panel táctico</span>
      </div>

      {message && (
        <div
          role={messageKind === 'error' ? 'alert' : 'status'}
          aria-live="polite"
          className={`rounded border p-3 text-sm ${messageKind === 'error' ? 'border-red-700 bg-red-950/50 text-red-200' : 'border-amber-800 bg-amber-950/30 text-amber-100'}`}
        >
          {message}
        </div>
      )}

      <div className="grid lg:grid-cols-[2fr,1fr] gap-6">
        <div className="grid md:grid-cols-2 gap-4">
          {loadingCatalog && units.length === 0 && (
            <div className="skeleton h-40 w-full md:col-span-2" role="status" aria-label="Cargando catálogo de tropas" />
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

        <section className="card p-5 space-y-4 lg:sticky lg:top-32 h-fit" aria-labelledby="troop-queue-heading">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 id="troop-queue-heading" className="text-xl sm:text-2xl">Cola de entrenamiento</h2>
              <p className="text-gray-400 text-sm">Revisa los tiempos en vivo</p>
            </div>
            <span className="badge shrink-0">Tiempo real</span>
          </div>
          <div className="space-y-3">
            {queues.troops?.length === 0 && <p className="text-gray-400">Sin entrenamientos activos</p>}
            {queues.troops?.map((queue) => (
              <div key={queue.id} className="glass-panel p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-yellow-200 break-words">
                    {queue.amount}x {t(queue.troop_type || queue.unit)}
                  </p>
                  <p className="text-xs text-gray-400">Entrenamiento en curso</p>
                </div>
                <div className="flex items-center justify-between sm:justify-end gap-3">
                  <Timer endTime={queue.finish_time || queue.finishAt} />
                  <button
                    type="button"
                    onClick={() => handleCancel(queue.id)}
                    disabled={busyQueueId === queue.id}
                    className="text-red-300 hover:text-red-200 text-xs underline rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400 disabled:opacity-50"
                    aria-label={`Cancelar entrenamiento de ${t(queue.troop_type || queue.unit)}`}
                  >
                    {busyQueueId === queue.id ? '…' : 'Cancelar'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};

export default TroopsView;
