import { memo } from 'react';
import GameIcon from '../GameIcon';

export const OASIS_RESOURCE_META = {
  wood: { icon: 'wood', label: 'Madera' },
  stone: { icon: 'stone', label: 'Piedra' },
  iron: { icon: 'iron', label: 'Hierro' },
  gold: { icon: 'gold', label: 'Oro' },
};

const tileColor = (type) => {
  switch (type) {
    case 'water': return 'bg-blue-500';
    case 'mountain': return 'bg-gray-600';
    case 'forest': return 'bg-green-800';
    default: return 'bg-green-500';
  }
};

const MapTile = memo(function MapTile({
  tile,
  isCenter,
  isSelected,
  isMine,
  isTabStop,
  onSelect,
  onFocusTile,
  onNavigate,
}) {
  const isOasis = Boolean(tile.oasis_id);
  let content = null;

  if (tile.city_id) {
    const settlementIcon = tile.settlement_type === 'camp' ? 'camp' : tile.points > 1000 ? 'castle' : 'house';
    content = (
      <div className={`w-8 h-8 mx-auto mt-2 rounded-full shadow-lg flex items-center justify-center ${isMine ? 'bg-blue-600 text-white' : tile.owner_id ? 'bg-red-600 text-white' : 'bg-gray-300 text-gray-950'}`}>
        <GameIcon name={settlementIcon} size={18} />
      </div>
    );
  } else if (isOasis) {
    const resourceMeta = OASIS_RESOURCE_META[tile.resource_type];
    content = (
      <div className={`w-8 h-8 mx-auto mt-2 rounded-full shadow-lg flex items-center justify-center ${tile.is_conquered ? (isMine ? 'bg-blue-500 ring-2 ring-blue-300' : 'bg-red-500 ring-2 ring-red-300') : 'bg-green-600 ring-2 ring-green-300'}`}>
        <GameIcon name={resourceMeta?.icon || 'oasis'} size={18} />
      </div>
    );
  }

  const settlementType = tile.settlement_type === 'camp' ? 'campamento' : 'ciudad';
  const oasisLabel = OASIS_RESOURCE_META[tile.resource_type]?.label || tile.resource_type || 'desconocido';
  const accessibleLabel = tile.city_id
    ? `Casilla ${tile.x}, ${tile.y}: ${settlementType} ${tile.city_name || ''}, ${tile.owner_name || 'Bárbaros'}`
    : isOasis
      ? `Casilla ${tile.x}, ${tile.y}: oasis de ${oasisLabel}`
      : `Casilla ${tile.x}, ${tile.y}: ${tile.type}`;

  return (
    <button
      type="button"
      className={`w-12 h-12 border border-black/20 relative cursor-pointer hover:brightness-110 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-300 ${tileColor(tile.type)} ${isSelected ? 'ring-2 ring-yellow-400 z-10' : ''}`}
      onClick={() => onSelect(tile)}
      onFocus={() => onFocusTile(tile)}
      onKeyDown={(event) => onNavigate(event, tile)}
      title={accessibleLabel}
      aria-label={accessibleLabel}
      aria-pressed={isSelected}
      tabIndex={isTabStop ? 0 : -1}
      data-testid={`map-tile-${tile.x}-${tile.y}`}
      data-map-coordinate={`${tile.x},${tile.y}`}
    >
      {content}
      {isCenter && <span className="absolute inset-0 border-2 border-white/50 pointer-events-none" aria-hidden="true" />}
    </button>
  );
});

export default MapTile;
