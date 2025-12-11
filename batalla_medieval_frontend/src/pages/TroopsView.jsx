import { useEffect } from 'react';
import TroopCard from '../components/TroopCard';
import Timer from '../components/Timer';
import { useCityStore } from '../store/cityStore';
import { troopList } from '../utils/gameMath';

const TroopsView = () => {
  const { queues, train, loadCity } = useCityStore();

  useEffect(() => {
    loadCity().catch(() => {});
  }, [loadCity]);

  const troops = troopList.map((name) => ({
    name,
    attack: 10,
    defense: 10,
    speed: 10,
    cost: { wood: 50, clay: 40, iron: 20 },
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Tropas</h1>
          <p className="text-gray-400">Entrena y organiza tus ejércitos</p>
        </div>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {troops.map((t) => (
          <TroopCard key={t.name} troop={t} onTrain={train} />
        ))}
      </div>
      <div>
        <h2 className="text-2xl mb-3">Cola de entrenamiento</h2>
        <div className="space-y-2">
          {queues.troops?.length === 0 && <p className="text-gray-400">Sin entrenamientos activos</p>}
          {queues.troops?.map((q, idx) => (
            <div key={idx} className="card p-3 flex items-center justify-between">
              <span>{q.amount}x {q.unit}</span>
              <Timer endTime={q.finishAt} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default TroopsView;
