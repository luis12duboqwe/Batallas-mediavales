import Timer from './Timer';
import { formatDate } from '../utils/format';

const colors = {
  attack: 'border-red-700/60 text-red-200 bg-red-900/20',
  attack_out: 'border-red-700/60 text-red-200 bg-red-900/20',
  attack_in: 'border-red-600/50 text-red-200 bg-red-900/20',
  spy: 'border-blue-700/60 text-blue-200 bg-blue-900/20',
  reinforce: 'border-green-700/60 text-green-200 bg-green-900/20',
};

const icons = {
  attack: '⚔️',
  attack_out: '⚔️',
  attack_in: '🛡️',
  spy: '🕵️',
  reinforce: '🛡️',
};

const MovementCard = ({ movement }) => {
  const tone = colors[movement.type] || colors[movement.category] || 'border-yellow-700/60 text-yellow-200 bg-yellow-900/20';
  const icon = icons[movement.type] || icons[movement.category] || '🧭';
  return (
    <div className={`card p-4 flex flex-col gap-3 relative overflow-hidden group ${tone} border`}
    >
      <div className="absolute inset-0 bg-gradient-to-br from-yellow-300/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition" />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg" aria-hidden>{icon}</span>
          <h3 className="text-lg capitalize">{movement.type?.replace('_', ' ')}</h3>
        </div>
        <span className="badge">{movement.status}</span>
      </div>
      <p className="text-sm text-gray-300">Origen: {movement.origin?.name} → Destino: {movement.target?.name}</p>
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span className="tooltip" data-tip="Fecha y hora estimada">Llegada: {formatDate(movement.arrivesAt)}</span>
        <Timer endTime={movement.arrivesAt} />
      </div>
    </div>
  );
};

export default MovementCard;
