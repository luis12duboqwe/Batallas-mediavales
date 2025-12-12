import { useEffect } from 'react';
import BuildingCard from '../components/BuildingCard';
import Timer from '../components/Timer';
import { useCityStore } from '../store/cityStore';

const BuildingsView = () => {
  const { buildings, queues, loadCity, upgrade, cancelBuilding } = useCityStore();

  useEffect(() => {
    loadCity().catch(() => {});
  }, [loadCity]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Edificios</h1>
          <p className="text-gray-400">Gestiona las mejoras de tu ciudad</p>
        </div>
      </div>

      {/* Building Queue */}
      {queues.buildings?.length > 0 && (
        <div className="card p-4 mb-6 border-yellow-800/50 bg-gray-900/50">
          <h3 className="text-xl mb-3 text-yellow-200">Cola de construcción</h3>
          <div className="space-y-2">
            {queues.buildings.map((q) => (
              <div key={q.id} className="flex items-center justify-between bg-gray-800/50 p-3 rounded border border-gray-700">
                <div>
                  <span className="font-bold text-yellow-100">{q.building_type}</span>
                  <span className="text-gray-400 text-sm ml-2">Nivel {q.target_level}</span>
                </div>
                <div className="flex items-center gap-4">
                  <Timer endTime={q.finish_time} />
                  <button 
                    onClick={() => cancelBuilding(q.id)}
                    className="text-red-400 hover:text-red-300 text-sm underline"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {buildings.map((b) => (
          <BuildingCard key={b.name} building={b} onUpgrade={upgrade} />
        ))}
      </div>
    </div>
  );
};

export default BuildingsView;
