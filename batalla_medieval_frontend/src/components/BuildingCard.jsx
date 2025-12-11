import Timer from './Timer';
import { formatNumber } from '../utils/format';

const BuildingCard = ({ building, onUpgrade }) => (
  <div className="card p-4 flex flex-col gap-3">
    <div className="flex items-center justify-between">
      <div>
        <h3 className="text-lg">{building.name}</h3>
        <p className="text-sm text-gray-400">Nivel {building.level}</p>
      </div>
      {building.upgradeEnds && <Timer endTime={building.upgradeEnds} />}
    </div>
    <div className="text-sm text-gray-300">
      <p>Producción: +{formatNumber(building.bonus || 0)}</p>
      <p>Coste: 🪵 {formatNumber(building.cost?.wood || 0)} | 🧱 {formatNumber(building.cost?.clay || 0)} | ⛓️ {formatNumber(building.cost?.iron || 0)}</p>
    </div>
    <button onClick={() => onUpgrade(building.name)} className="btn-primary w-full">Mejorar</button>
  </div>
);

export default BuildingCard;
