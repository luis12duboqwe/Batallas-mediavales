import Timer from './Timer';
import { formatNumber } from '../utils/format';

const buildingIcons = {
  Ayuntamiento: '🏛️',
  Cuartel: '🛡️',
  Mina: '⛏️',
  Aserradero: '🪵',
  Ladrillar: '🧱',
};

const BuildingCard = ({ building, onUpgrade }) => (
  <div className="card p-5 flex flex-col gap-4 relative overflow-hidden group transition duration-200 hover:-translate-y-1 hover:shadow-[0_18px_45px_rgba(0,0,0,0.45)]">
    <div className="absolute inset-0 bg-gradient-to-br from-yellow-500/5 via-transparent to-transparent pointer-events-none opacity-0 group-hover:opacity-100 transition" />
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-center gap-3">
        <div className="h-12 w-12 rounded-xl bg-gray-800/80 border border-yellow-800/50 flex items-center justify-center text-2xl shadow-inner">
          {buildingIcons[building.name] || '🏰'}
        </div>
        <div>
          <h3 className="text-lg leading-tight">{building.name}</h3>
          <p className="text-sm text-gray-400">Nivel {building.level}</p>
        </div>
      </div>
      {building.upgradeEnds && <Timer endTime={building.upgradeEnds} />}
    </div>
    <div className="grid grid-cols-2 gap-3 text-sm text-gray-300">
      <p className="tooltip" data-tip="Producción por nivel">
        Producción: <span className="text-yellow-200">+{formatNumber(building.bonus || 0)}</span>
      </p>
      <p className="tooltip" data-tip="Recurso necesario para la próxima mejora">
        Coste: 🪵 {formatNumber(building.cost?.wood || 0)} | 🧱 {formatNumber(building.cost?.clay || 0)} | ⛓️ {formatNumber(building.cost?.iron || 0)}
      </p>
    </div>
    <div className="flex items-center justify-between text-xs text-gray-400">
      <span>Tiempo de mejora</span>
      <span className="text-yellow-200">{building.cost?.time ? `${building.cost.time}s` : 'Instantáneo'}</span>
    </div>
    <button
      onClick={() => onUpgrade(building.name)}
      className="btn-primary w-full"
    >
      Mejorar
    </button>
    <div className="floating-panel">
      <span className="text-yellow-200">Próximo nivel</span>
      <span className="font-semibold">Nivel {building.level + 1}</span>
    </div>
  </div>
);

export default BuildingCard;
