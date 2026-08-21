import { useEffect } from 'react';
import MovementCard from '../components/MovementCard';
import { useCityStore } from '../store/cityStore';

const categoryMeta = [
  ['attack_out', 'Ataques salientes', 'bg-red-900/40 text-red-200 border-red-700/50'],
  ['attack_in', 'Ataques entrantes', 'bg-amber-900/40 text-amber-200 border-amber-700/50'],
  ['spy_out', 'Espionaje saliente', 'bg-blue-900/40 text-blue-200 border-blue-700/50'],
  ['spy_in', 'Espionaje entrante', 'bg-blue-900/40 text-blue-200 border-blue-700/50'],
  ['reinforce_out', 'Refuerzos enviados', 'bg-green-900/40 text-green-200 border-green-700/50'],
  ['reinforce_in', 'Refuerzos recibidos', 'bg-green-900/40 text-green-200 border-green-700/50'],
  ['transport_out', 'Transportes enviados', 'bg-cyan-900/40 text-cyan-200 border-cyan-700/50'],
  ['transport_in', 'Transportes recibidos', 'bg-cyan-900/40 text-cyan-200 border-cyan-700/50'],
  ['return', 'Retornos', 'bg-yellow-900/40 text-yellow-200 border-yellow-700/50'],
];

const MovementsView = () => {
  const { movements, loadMovements } = useCityStore();

  useEffect(() => {
    loadMovements().catch(() => {});
  }, [loadMovements]);

  const visibleCategories = categoryMeta.filter(([category]) =>
    movements.some((movement) => movement.category === category)
  );
  const knownCategories = new Set(categoryMeta.map(([category]) => category));
  const otherMovements = movements.filter((movement) => !knownCategories.has(movement.category));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Movimientos</h1>
        <p className="text-gray-400">Ataques, espionaje, refuerzos, transportes y retornos</p>
      </div>

      {movements.length === 0 && (
        <div className="glass-panel p-4 text-gray-400 text-sm" role="status">
          No hay movimientos activos o recientes en este mundo.
        </div>
      )}

      {visibleCategories.map(([category, title, badgeClass]) => {
        const categoryMovements = movements.filter((movement) => movement.category === category);
        return (
          <section key={category} className="space-y-3" aria-labelledby={`movement-${category}`}>
            <div className="flex flex-wrap items-center gap-3">
              <h2 id={`movement-${category}`} className="text-2xl">{title}</h2>
              <span className={`badge ${badgeClass}`}>{categoryMovements.length}</span>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
              {categoryMovements.map((movement) => (
                <MovementCard key={movement.id} movement={movement} />
              ))}
            </div>
          </section>
        );
      })}

      {otherMovements.length > 0 && (
        <section className="space-y-3" aria-labelledby="movement-other">
          <h2 id="movement-other" className="text-2xl">Otros movimientos</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {otherMovements.map((movement) => (
              <MovementCard key={movement.id} movement={movement} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default MovementsView;
