import { useEffect, useState } from 'react';
import { api } from '../api/axiosClient';
import { useUserStore } from '../store/userStore';
import { useCityStore } from '../store/cityStore';
import { useNavigate } from 'react-router-dom';
import GameIcon from '../components/GameIcon';

const RADIUS = 7;
const OASIS_RESOURCE_META = {
  wood: { icon: 'wood', label: 'Madera' },
  stone: { icon: 'stone', label: 'Piedra' },
  iron: { icon: 'iron', label: 'Hierro' },
  gold: { icon: 'gold', label: 'Oro' },
};

const PveDifficulty = ({ tile }) => {
  if (!tile?.pve_tier) return null;
  return (
    <div className="rounded border border-amber-700/40 bg-amber-950/30 p-2 text-xs text-amber-100" data-testid="pve-difficulty" data-pve-tier={tile.pve_tier} data-pve-rules-version={tile.pve_rules_version || ''}>
      <div className="font-semibold">Dificultad PvE T{tile.pve_tier}</div>
      {tile.pve_rules_version && <div className="mt-1 break-all text-[10px] text-gray-400">Reglas {tile.pve_rules_version}</div>}
    </div>
  );
};

const MapView = () => {
  const { user } = useUserStore();
  const { currentCity } = useCityStore();
  const navigate = useNavigate();
  const [center, setCenter] = useState({ x: 0, y: 0 });
  const [tiles, setTiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedTile, setSelectedTile] = useState(null);
  const [jumpCoords, setJumpCoords] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (currentCity) {
      setCenter({ x: currentCity.x ?? 0, y: currentCity.y ?? 0 });
      setJumpCoords({ x: currentCity.x ?? 0, y: currentCity.y ?? 0 });
    }
  }, [currentCity]);

  useEffect(() => {
    if (user?.world_id) fetchTiles();
  }, [center, user?.world_id]);

  const fetchTiles = async () => {
    setLoading(true);
    try {
      const res = await api.getMapTiles(user.world_id, center.x, center.y, RADIUS);
      setTiles(res.data.tiles);
    } catch (error) {
      console.error('Failed to load map', error);
    } finally {
      setLoading(false);
    }
  };

  const handleJump = (event) => {
    event.preventDefault();
    setCenter({ x: parseInt(jumpCoords.x), y: parseInt(jumpCoords.y) });
  };

  const handleMove = (dx, dy) => setCenter((previous) => ({ x: previous.x + dx, y: previous.y + dy }));

  const getTileColor = (type) => {
    switch (type) {
      case 'water': return 'bg-blue-500';
      case 'mountain': return 'bg-gray-600';
      case 'forest': return 'bg-green-800';
      default: return 'bg-green-500';
    }
  };

  const renderTile = (tile) => {
    const isCenter = tile.x === center.x && tile.y === center.y;
    const isSelected = selectedTile && selectedTile.x === tile.x && selectedTile.y === tile.y;
    const isMine = Boolean(user?.id && tile.owner_id === user.id);
    const isOasis = !!tile.oasis_id;
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
        <div className={`w-8 h-8 mx-auto mt-2 rounded-full shadow-lg flex items-center justify-center ${tile.is_conquered ? (tile.owner_id === user?.id ? 'bg-blue-500 ring-2 ring-blue-300' : 'bg-red-500 ring-2 ring-red-300') : 'bg-green-600 ring-2 ring-green-300'}`}>
          <GameIcon name={resourceMeta?.icon || 'oasis'} size={18} />
        </div>
      );
    }

    const settlementType = tile.settlement_type === 'camp' ? 'campamento' : 'ciudad';
    const oasisLabel = OASIS_RESOURCE_META[tile.resource_type]?.label || tile.resource_type;
    const accessibleLabel = tile.city_id
      ? `Casilla ${tile.x}, ${tile.y}: ${settlementType} ${tile.city_name || ''}, ${tile.owner_name || 'Bárbaros'}`
      : isOasis
        ? `Casilla ${tile.x}, ${tile.y}: oasis de ${oasisLabel}`
        : `Casilla ${tile.x}, ${tile.y}: ${tile.type}`;

    return (
      <button
        type="button"
        key={`${tile.x},${tile.y}`}
        className={`w-12 h-12 border border-black/20 relative cursor-pointer hover:brightness-110 transition ${getTileColor(tile.type)} ${isSelected ? 'ring-2 ring-yellow-400 z-10' : ''}`}
        onClick={() => setSelectedTile(tile)}
        title={`(${tile.x}, ${tile.y}) ${tile.type}`}
        aria-label={accessibleLabel}
        aria-pressed={Boolean(isSelected)}
        data-testid={`map-tile-${tile.x}-${tile.y}`}
      >
        {content}
        {isCenter && <span className="absolute inset-0 border-2 border-white/50 pointer-events-none" aria-hidden="true" />}
      </button>
    );
  };

  const sortedTiles = [...tiles].sort((a, b) => (a.y !== b.y ? b.y - a.y : a.x - b.x));
  const rows = {};
  sortedTiles.forEach((tile) => {
    if (!rows[tile.y]) rows[tile.y] = [];
    rows[tile.y].push(tile);
  });
  const sortedY = Object.keys(rows).sort((a, b) => b - a);
  const selectedOasisResource = selectedTile?.oasis_id ? OASIS_RESOURCE_META[selectedTile.resource_type] : null;
  const selectedSettlementLabel = selectedTile?.settlement_type === 'camp' ? 'Campamento' : 'Ciudad';
  const selectedSettlementIsMine = Boolean(user?.id && selectedTile?.owner_id === user.id);

  return (
    <div className="p-2 sm:p-4 h-full flex flex-col min-w-0">
      <div className="flex flex-col gap-3 mb-4 bg-black/40 p-4 rounded sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-amber-500">Mapa Global</h1>
        <form onSubmit={handleJump} className="grid w-full grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-2 sm:w-auto" aria-label="Ir a coordenadas">
          <input type="number" aria-label="Coordenada X" className="input input-sm min-w-0 w-full bg-black/50" placeholder="X" value={jumpCoords.x} onChange={(event) => setJumpCoords({ ...jumpCoords, x: event.target.value })} />
          <input type="number" aria-label="Coordenada Y" className="input input-sm min-w-0 w-full bg-black/50" placeholder="Y" value={jumpCoords.y} onChange={(event) => setJumpCoords({ ...jumpCoords, y: event.target.value })} />
          <button type="submit" className="btn btn-sm btn-primary">Ir</button>
        </form>
      </div>

      <div className="flex flex-1 min-w-0 flex-col gap-4 lg:flex-row lg:overflow-hidden">
        <div className="min-h-[28rem] min-w-0 flex-1 relative bg-gray-900 rounded overflow-auto p-4" data-testid="map-grid-panel">
          {loading && <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20" role="status">Cargando...</div>}
          <div className="relative w-max mx-auto p-10" data-testid="map-grid-content">
            <button type="button" aria-label="Mover mapa hacia arriba" onClick={() => handleMove(0, 5)} className="absolute top-2 left-1/2 -translate-x-1/2 btn btn-xs btn-circle"><GameIcon name="arrowUp" size={18} /></button>
            <button type="button" aria-label="Mover mapa hacia abajo" onClick={() => handleMove(0, -5)} className="absolute bottom-2 left-1/2 -translate-x-1/2 btn btn-xs btn-circle"><GameIcon name="arrowDown" size={18} /></button>
            <button type="button" aria-label="Mover mapa hacia la izquierda" onClick={() => handleMove(-5, 0)} className="absolute left-2 top-1/2 -translate-y-1/2 btn btn-xs btn-circle"><GameIcon name="arrowLeft" size={18} /></button>
            <button type="button" aria-label="Mover mapa hacia la derecha" onClick={() => handleMove(5, 0)} className="absolute right-2 top-1/2 -translate-y-1/2 btn btn-xs btn-circle"><GameIcon name="arrowRight" size={18} /></button>
            <div className="grid gap-0.5 bg-black/50 p-1" role="group" aria-label="Cuadrícula del mapa">
              {sortedY.map((y) => (
                <div key={y} className="flex gap-0.5">
                  {rows[y].sort((a, b) => a.x - b.x).map((tile) => renderTile(tile))}
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside className="w-full shrink-0 bg-gray-800 p-4 rounded shadow-lg border border-gray-700 flex flex-col lg:w-80" aria-label="Detalles de la casilla seleccionada" data-testid="map-details-panel">
          <h2 className="text-xl font-bold text-amber-400 mb-4">Detalles</h2>
          {selectedTile ? (
            <div className="space-y-4">
              <div className="bg-gray-700 p-3 rounded">
                <div className="text-sm text-gray-400">Coordenadas</div>
                <div className="text-2xl font-mono text-white">({selectedTile.x}, {selectedTile.y})</div>
                <div className="text-sm text-green-400 capitalize mt-1">{selectedTile.type}</div>
              </div>

              {selectedTile.city_id ? (
                <div className="space-y-3">
                  <div>
                    <div className="text-sm text-gray-400">{selectedSettlementLabel}</div>
                    <div className="font-bold text-lg text-white flex items-center gap-2"><GameIcon name={selectedTile.settlement_type === 'camp' ? 'camp' : 'castle'} size={20} />{selectedTile.city_name}</div>
                    <div className="text-xs text-yellow-500">{selectedTile.points} puntos</div>
                  </div>
                  <div><div className="text-sm text-gray-400">Jugador</div><div className="font-bold text-white">{selectedTile.owner_name || 'Bárbaros'}</div></div>
                  {!selectedTile.owner_id && <PveDifficulty tile={selectedTile} />}
                  {selectedTile.alliance_name && <div><div className="text-sm text-gray-400">Alianza</div><div className="font-bold text-blue-400">[{selectedTile.alliance_name}]</div></div>}
                  {selectedSettlementIsMine && <div className="rounded border border-blue-700/50 bg-blue-950/30 p-2 text-xs text-blue-200">Este asentamiento te pertenece.</div>}
                  <div className="divider" />
                  {currentCity && !selectedSettlementIsMine && (
                    <div className="grid grid-cols-2 gap-2">
                      <button type="button" className="btn btn-sm btn-error w-full" onClick={() => navigate(`/send-movement/${selectedTile.city_id}`)}>Atacar</button>
                      <button type="button" className="btn btn-sm btn-info w-full">Espiar</button>
                      <button type="button" className="btn btn-sm btn-success w-full">Comerciar</button>
                      <button type="button" className="btn btn-sm btn-warning w-full">Mensaje</button>
                    </div>
                  )}
                </div>
              ) : selectedTile.oasis_id ? (
                <div className="space-y-3">
                  <div><div className="text-sm text-gray-400">Oasis</div><div className="font-bold text-lg text-white flex items-center gap-2"><GameIcon name={selectedOasisResource?.icon || 'oasis'} size={20} />{selectedOasisResource?.label || selectedTile.resource_type} (+{selectedTile.bonus_percent}%)</div></div>
                  <PveDifficulty tile={selectedTile} />
                  <div><div className="text-sm text-gray-400">Estado</div><div className="font-bold text-white">{selectedTile.is_conquered ? (selectedTile.owner_id ? 'Conquistado' : 'Ocupado') : 'Salvaje'}</div></div>
                  {currentCity && <div className="grid grid-cols-2 gap-2"><button type="button" className="btn btn-sm btn-error w-full" onClick={() => navigate(`/send-movement/${selectedTile.oasis_id}?type=oasis`)}>Atacar</button><button type="button" className="btn btn-sm btn-info w-full">Espiar</button></div>}
                </div>
              ) : (
                <div className="text-gray-500 italic mt-4">Terreno salvaje. No hay asentamientos aquí.</div>
              )}
            </div>
          ) : (
            <div className="text-gray-500 text-center mt-10">Selecciona una casilla en el mapa para ver información.</div>
          )}
        </aside>
      </div>
    </div>
  );
};

export default MapView;
