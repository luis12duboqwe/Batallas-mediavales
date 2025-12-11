import { useEffect } from 'react';
import MovementCard from '../components/MovementCard';
import { useCityStore } from '../store/cityStore';

const MovementsView = () => {
  const { movements, loadMovements } = useCityStore();

  useEffect(() => {
    loadMovements().catch(() => {});
  }, [loadMovements]);

  const categories = ['attack_out', 'attack_in', 'spy', 'reinforce'];

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
          <h2 className="text-2xl capitalize">{cat.replace('_', ' ')}</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {movements.filter((m) => m.category === cat).map((m) => (
              <MovementCard key={m.id} movement={m} />
            ))}
          </div>
          {movements.filter((m) => m.category === cat).length === 0 && (
            <p className="text-gray-500">No hay movimientos en esta categoría</p>
          )}
        </div>
      ))}
    </div>
  );
};

export default MovementsView;
