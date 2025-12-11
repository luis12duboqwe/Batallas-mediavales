import { useEffect } from 'react';
import MovementCard from '../components/MovementCard';
import { useCityStore } from '../store/cityStore';

const MovementsView = () => {
  const { movements, loadMovements } = useCityStore();

  useEffect(() => {
    loadMovements().catch(() => {});
  }, [loadMovements]);

  const categories = ['attack_out', 'attack_in', 'spy', 'reinforce'];
  const categoryTitles = {
    attack_out: 'Ataques salientes',
    attack_in: 'Ataques entrantes',
    spy: 'Espionaje',
    reinforce: 'Refuerzos',
  };
  const categoryBadges = {
    attack_out: 'bg-red-900/40 text-red-200 border-red-700/50',
    attack_in: 'bg-amber-900/40 text-amber-200 border-amber-700/50',
    spy: 'bg-blue-900/40 text-blue-200 border-blue-700/50',
    reinforce: 'bg-green-900/40 text-green-200 border-green-700/50',
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Movimientos</h1>
          <p className="text-gray-400">Ataques, espías y refuerzos</p>
        </div>
      </div>
      {categories.map((cat) => (
        <div key={cat} className="space-y-3">
          <div className="flex items-center gap-3">
            <h2 className="text-2xl capitalize">{categoryTitles[cat] || cat.replace('_', ' ')}</h2>
            <span className={`badge ${categoryBadges[cat]}`}>en vivo</span>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {movements.filter((m) => m.category === cat).map((m) => (
              <MovementCard key={m.id} movement={m} />
            ))}
          </div>
          {movements.filter((m) => m.category === cat).length === 0 && (
            <div className="glass-panel p-4 text-gray-400 text-sm">No hay movimientos en esta categoría</div>
          )}
        </div>
      ))}
    </div>
  );
};

export default MovementsView;
