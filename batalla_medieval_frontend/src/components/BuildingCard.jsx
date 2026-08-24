import Timer from './Timer';
import { formatNumber } from '../utils/format';

const buildingIcons = {
  town_hall: '🏛️',
  barracks: '🛡️',
  stable: '🐎',
  wall: '🧱',
  market: '⚖️',
  farm: '🌾',
  warehouse: '📦',
  smithy: '⚒️',
  workshop: '⚙️',
  church: '⛪',
  cathedral: '🕍',
  world_wonder: '🌟',
};

const resourceMeta = [
  ['wood', '🪵'],
  ['stone', '🪨'],
  ['iron', '⛓️'],
  ['gold', '🪙'],
];

const BuildingCard = ({ building, onUpgrade }) => {
  const displayName = building.display_name || building.name;
  const safeName = building.name.toLowerCase().replace(/\s+/g, '-');
  const visibleCosts = resourceMeta.filter(
    ([resource]) => Number(building.cost?.[resource] ?? 0) > 0,
  );

  return (
    <article className={`card p-5 flex flex-col gap-4 relative overflow-hidden group transition duration-200 hover:-translate-y-1 hover:shadow-[0_18px_45px_rgba(0,0,0,0.45)] building-card-${safeName}`}>
      <div className="absolute inset-0 bg-gradient-to-br from-yellow-500/5 via-transparent to-transparent pointer-events-none opacity-0 group-hover:opacity-100 transition" />
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-12 w-12 shrink-0 rounded-xl bg-gray-800/80 border border-yellow-800/50 flex items-center justify-center text-2xl shadow-inner" aria-hidden>
            {buildingIcons[building.name] || '🏰'}
          </div>
          <div className="min-w-0">
            <h3 className="text-lg leading-tight break-words">{displayName}</h3>
            <p className="text-sm text-gray-400">Nivel {building.level}</p>
          </div>
        </div>
        {building.upgradeEnds && <Timer endTime={building.upgradeEnds} />}
      </div>

      <div className="text-sm text-gray-300">
        <p className="leading-relaxed flex flex-wrap gap-x-2 gap-y-1">
          <span>Coste próximo nivel:</span>
          {visibleCosts.map(([resource, icon], index) => (
            <span key={resource}>
              {index > 0 ? '· ' : ''}{icon} {formatNumber(building.cost?.[resource] ?? 0)}
            </span>
          ))}
        </p>
      </div>

      <div className="flex items-center justify-between gap-3 text-xs text-gray-400">
        <span>Tiempo de mejora</span>
        <span className="text-yellow-200 text-right">{building.build_time ? `${building.build_time}s` : 'Instantáneo'}</span>
      </div>

      <button
        type="button"
        onClick={() => onUpgrade(building.name)}
        disabled={building.requirements_met === false}
        className={`btn-primary w-full upgrade-btn-${safeName} focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-200 ${building.requirements_met === false ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        {building.level === 0 ? 'Construir' : 'Mejorar'}
      </button>

      {building.requirements_met === false && (
        <div className="text-xs text-red-300 mt-2" role="status">
          Requisitos: {Object.entries(building.requirements || {}).map(([name, level]) => `${name} ${level}`).join(', ')}
        </div>
      )}

      <div className="floating-panel">
        <span className="text-yellow-200">Próximo nivel</span>
        <span className="font-semibold">Nivel {building.level + 1}</span>
      </div>
    </article>
  );
};

export default BuildingCard;
