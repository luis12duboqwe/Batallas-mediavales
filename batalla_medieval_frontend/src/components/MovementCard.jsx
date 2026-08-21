import Timer from './Timer';
import { formatDate } from '../utils/format';

const colors = {
  attack_out: 'border-red-700/60 text-red-200 bg-red-900/20',
  attack_in: 'border-red-600/50 text-red-200 bg-red-900/20',
  spy_out: 'border-blue-700/60 text-blue-200 bg-blue-900/20',
  spy_in: 'border-blue-600/50 text-blue-200 bg-blue-900/20',
  reinforce_out: 'border-green-700/60 text-green-200 bg-green-900/20',
  reinforce_in: 'border-green-600/50 text-green-200 bg-green-900/20',
  transport_out: 'border-cyan-700/60 text-cyan-200 bg-cyan-900/20',
  transport_in: 'border-cyan-600/50 text-cyan-200 bg-cyan-900/20',
  return: 'border-yellow-700/60 text-yellow-200 bg-yellow-900/20',
};

const icons = {
  attack_out: '⚔️',
  attack_in: '🛡️',
  spy_out: '🕵️',
  spy_in: '👁️',
  reinforce_out: '🛡️',
  reinforce_in: '🤝',
  transport_out: '📦',
  transport_in: '📥',
  return: '↩️',
};

const movementLabels = {
  attack: 'Ataque',
  spy: 'Espionaje',
  reinforce: 'Refuerzo',
  transport: 'Transporte',
  return: 'Retorno',
};

const statusLabels = {
  ongoing: 'En camino',
  resolved: 'Resuelto',
  completed: 'Completado',
  cancelled: 'Cancelado',
};

const MovementCard = ({ movement }) => {
  const tone = colors[movement.category] || 'border-yellow-700/60 text-yellow-200 bg-yellow-900/20';
  const icon = icons[movement.category] || '🧭';
  const typeLabel = movementLabels[movement.movement_type] || movement.movement_type || 'Movimiento';
  const directionLabel = movement.category?.endsWith('_in')
    ? 'Entrante'
    : movement.category?.endsWith('_out')
      ? 'Saliente'
      : null;
  const targetLabel = movement.target_city_id
    ? `Ciudad #${movement.target_city_id}`
    : movement.target_oasis_id
      ? `Oasis #${movement.target_oasis_id}`
      : 'Destino no disponible';

  return (
    <article className={`card p-4 flex flex-col gap-3 relative overflow-hidden group ${tone} border`}>
      <div className="absolute inset-0 bg-gradient-to-br from-yellow-300/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition pointer-events-none" />
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-lg" aria-hidden>{icon}</span>
          <h3 className="text-lg truncate">
            {typeLabel}{directionLabel ? ` · ${directionLabel}` : ''}
          </h3>
        </div>
        <span className="badge shrink-0">{statusLabels[movement.status] || movement.status}</span>
      </div>
      <p className="text-sm text-gray-300 break-words">
        Ciudad #{movement.origin_city_id} → {targetLabel}
      </p>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs text-gray-400">
        <span className="tooltip" data-tip="Fecha y hora estimada">
          Llegada: {formatDate(movement.arrival_time)}
        </span>
        {movement.status === 'ongoing' && <Timer endTime={movement.arrival_time} />}
      </div>
    </article>
  );
};

export default MovementCard;
