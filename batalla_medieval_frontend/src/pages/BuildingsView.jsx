import { useEffect, useState } from 'react';
import BuildingCard from '../components/BuildingCard';
import Timer from '../components/Timer';
import { useCityStore } from '../store/cityStore';

const BuildingsView = () => {
  const { buildings, queues, loadCity, upgrade, cancelBuilding } = useCityStore();
  const [message, setMessage] = useState('');
  const [messageKind, setMessageKind] = useState('status');
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    loadCity().catch(() => {
      setMessageKind('error');
      setMessage('No se pudo cargar el estado de edificios.');
    });
  }, [loadCity]);

  const displayName = (buildingType) => (
    buildings.find((building) => building.name === buildingType)?.display_name || buildingType
  );

  const handleUpgrade = async (buildingType) => {
    setBusyId(`upgrade-${buildingType}`);
    setMessage('');
    try {
      await upgrade(buildingType);
      setMessageKind('status');
      setMessage('Mejora añadida a la cola.');
    } catch (error) {
      setMessageKind('error');
      setMessage(error.response?.data?.detail?.message || error.response?.data?.detail || 'No se pudo iniciar la mejora.');
    } finally {
      setBusyId(null);
    }
  };

  const handleCancel = async (queueId) => {
    setBusyId(`queue-${queueId}`);
    setMessage('');
    try {
      await cancelBuilding(queueId);
      setMessageKind('status');
      setMessage('Mejora cancelada y recursos actualizados.');
    } catch (error) {
      setMessageKind('error');
      setMessage(error.response?.data?.detail?.message || error.response?.data?.detail || 'No se pudo cancelar la mejora.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl">Edificios</h1>
        <p className="text-gray-400">Gestiona las mejoras de tu ciudad</p>
      </div>

      {message && (
        <div
          role={messageKind === 'error' ? 'alert' : 'status'}
          aria-live="polite"
          className={`rounded border p-3 text-sm ${messageKind === 'error' ? 'border-red-700 bg-red-950/50 text-red-200' : 'border-green-700 bg-green-950/40 text-green-200'}`}
        >
          {message}
        </div>
      )}

      {queues.buildings?.length > 0 && (
        <section className="card p-4 mb-6 border-yellow-800/50 bg-gray-900/50" aria-labelledby="building-queue-heading">
          <h2 id="building-queue-heading" className="text-xl mb-3 text-yellow-200">Cola de construcción</h2>
          <div className="space-y-2">
            {queues.buildings.map((queue) => (
              <div key={queue.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-gray-800/50 p-3 rounded border border-gray-700">
                <div className="min-w-0">
                  <span className="font-bold text-yellow-100 break-words">{displayName(queue.building_type)}</span>
                  <span className="text-gray-400 text-sm ml-2">Nivel {queue.target_level}</span>
                </div>
                <div className="flex items-center justify-between sm:justify-end gap-4">
                  <Timer endTime={queue.finish_time} />
                  <button
                    type="button"
                    onClick={() => handleCancel(queue.id)}
                    disabled={busyId === `queue-${queue.id}`}
                    className="text-red-300 hover:text-red-200 text-sm underline rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-400 disabled:opacity-50"
                  >
                    {busyId === `queue-${queue.id}` ? 'Cancelando…' : 'Cancelar'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {buildings.map((building) => (
          <div key={building.name} aria-busy={busyId === `upgrade-${building.name}`}>
            <BuildingCard building={building} onUpgrade={handleUpgrade} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default BuildingsView;
