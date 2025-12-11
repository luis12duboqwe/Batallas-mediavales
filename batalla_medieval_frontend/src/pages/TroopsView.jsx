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
        <span className="badge">Panel táctico</span>
      </div>
      <div className="grid lg:grid-cols-[2fr,1fr] gap-6">
        <div className="grid md:grid-cols-2 gap-4">
          {troops.map((t) => (
            <TroopCard key={t.name} troop={t} onTrain={train} />
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
            {queues.troops?.length === 0 && (
              <div className="skeleton h-12 w-full" />
            )}
            {queues.troops?.length === 0 && <p className="text-gray-400">Sin entrenamientos activos</p>}
            {queues.troops?.map((q, idx) => (
              <div key={idx} className="glass-panel p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-yellow-200">{q.amount}x {q.unit}</p>
                  <p className="text-xs text-gray-400">Entrenamiento en curso</p>
                </div>
                <Timer endTime={q.finishAt} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default TroopsView;
