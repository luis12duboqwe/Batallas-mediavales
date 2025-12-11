import Timer from './Timer';
import { formatDate } from '../utils/format';

const MovementCard = ({ movement }) => (
  <div className="card p-4 flex flex-col gap-2">
    <div className="flex items-center justify-between">
      <h3 className="text-lg capitalize">{movement.type}</h3>
      <span className="badge">{movement.status}</span>
    </div>
    <p className="text-sm text-gray-300">Origen: {movement.origin?.name} → Destino: {movement.target?.name}</p>
    <p className="text-sm text-gray-400">Llegada: {formatDate(movement.arrivesAt)}</p>
    <Timer endTime={movement.arrivesAt} />
  </div>
);

export default MovementCard;
