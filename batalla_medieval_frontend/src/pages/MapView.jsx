import { useEffect, useState } from 'react';
import { api } from '../api/axiosClient';
import { useUserStore } from '../store/userStore';
import { useCityStore } from '../store/cityStore';
import { useNavigate } from 'react-router-dom';

const TILE_SIZE = 50;
const RADIUS = 7; // 15x15 grid

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
    if (user?.world_id) {
      fetchTiles();
    }
  }, [center, user?.world_id]);

  const fetchTiles = async () => {
    setLoading(true);
    try {
      const res = await api.getMapTiles(user.world_id, center.x, center.y, RADIUS);
      setTiles(res.data.tiles);
    } catch (error) {
      console.error("Failed to load map", error);
    } finally {
      setLoading(false);
    }
  };

  const handleJump = (e) => {
    e.preventDefault();
    setCenter({ x: parseInt(jumpCoords.x), y: parseInt(jumpCoords.y) });
  };

  const handleMove = (dx, dy) => {
    setCenter(prev => ({ x: prev.x + dx, y: prev.y + dy }));
  };

  const getTileColor = (type) => {
    switch (type) {
      case 'water': return 'bg-blue-500';
      case 'mountain': return 'bg-gray-600';
      case 'forest': return 'bg-green-800';
      default: return 'bg-green-500'; // grass
    }
  };

  const renderTile = (tile) => {
    const isCenter = tile.x === center.x && tile.y === center.y;
    const isSelected = selectedTile && selectedTile.x === tile.x && selectedTile.y === tile.y;
    const isMyCity = currentCity && tile.city_id === currentCity.id;
    const isOasis = !!tile.oasis_id;

    let content = null;
    if (tile.city_id) {
        content = (
          <div className={`
            w-8 h-8 mx-auto mt-2 rounded-full shadow-lg flex items-center justify-center text-xs font-bold
            ${isMyCity ? 'bg-blue-600 text-white' : tile.owner_id ? 'bg-red-600 text-white' : 'bg-gray-400 text-black'}
          `}>
            {tile.points > 1000 ? '🏰' : '🏠'}
          </div>
        );
    } else if (isOasis) {
        const resourceIcons = { wood: '🌲', clay: '🧱', iron: '⛏️', crop: '🌾' };
        content = (
            <div className={`
                w-8 h-8 mx-auto mt-2 rounded-full shadow-lg flex items-center justify-center text-xs font-bold
                ${tile.is_conquered ? (tile.owner_id === user?.id ? 'bg-blue-500 ring-2 ring-blue-300' : 'bg-red-500 ring-2 ring-red-300') : 'bg-green-600 ring-2 ring-green-300'}
            `}>
                {resourceIcons[tile.resource_type] || '🌴'}
            </div>
        );
    }

    return (
      <div
        key={`${tile.x},${tile.y}`}
        className={`
          w-12 h-12 border border-black/20 relative cursor-pointer hover:brightness-110 transition
          ${getTileColor(tile.type)}
          ${isSelected ? 'ring-2 ring-yellow-400 z-10' : ''}
        `}
        onClick={() => setSelectedTile(tile)}
        title={`(${tile.x}, ${tile.y}) ${tile.type}`}
      >
        {content}
        {isCenter && <div className="absolute inset-0 border-2 border-white/50 pointer-events-none"></div>}
      </div>
    );
  };

  // Organize tiles into a grid
  // We need to sort them by Y then X to render in rows
  const sortedTiles = [...tiles].sort((a, b) => {
    if (a.y !== b.y) return b.y - a.y; // Top to bottom (Max Y first)
    return a.x - b.x; // Left to right (Min X first)
  });

  // Group by Y
  const rows = {};
  sortedTiles.forEach(tile => {
    if (!rows[tile.y]) rows[tile.y] = [];
    rows[tile.y].push(tile);
  });
  
  // Sort rows by Y descending
  const sortedY = Object.keys(rows).sort((a, b) => b - a);

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="flex justify-between items-center mb-4 bg-black/40 p-4 rounded">
        <h1 className="text-2xl font-bold text-amber-500">Mapa Global</h1>
        
        <form onSubmit={handleJump} className="flex gap-2">
          <input 
            type="number" 
            className="input input-sm w-20 bg-black/50" 
            placeholder="X"
            value={jumpCoords.x}
            onChange={e => setJumpCoords({...jumpCoords, x: e.target.value})}
          />
          <input 
            type="number" 
            className="input input-sm w-20 bg-black/50" 
            placeholder="Y"
            value={jumpCoords.y}
            onChange={e => setJumpCoords({...jumpCoords, y: e.target.value})}
          />
          <button type="submit" className="btn btn-sm btn-primary">Ir</button>
        </form>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden">
        {/* Map Area */}
        <div className="flex-1 relative bg-gray-900 rounded overflow-auto flex items-center justify-center p-4">
          {loading && <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20">Cargando...</div>}
          
          <div className="relative">
            {/* Navigation Arrows Overlay */}
            <button onClick={() => handleMove(0, 5)} className="absolute top-0 left-1/2 -translate-x-1/2 -mt-8 btn btn-xs btn-circle">⬆️</button>
            <button onClick={() => handleMove(0, -5)} className="absolute bottom-0 left-1/2 -translate-x-1/2 -mb-8 btn btn-xs btn-circle">⬇️</button>
            <button onClick={() => handleMove(-5, 0)} className="absolute left-0 top-1/2 -translate-y-1/2 -ml-8 btn btn-xs btn-circle">⬅️</button>
            <button onClick={() => handleMove(5, 0)} className="absolute right-0 top-1/2 -translate-y-1/2 -mr-8 btn btn-xs btn-circle">➡️</button>

            <div className="grid gap-0.5 bg-black/50 p-1">
              {sortedY.map(y => (
                <div key={y} className="flex gap-0.5">
                  {rows[y].sort((a, b) => a.x - b.x).map(tile => renderTile(tile))}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Info Panel */}
        <div className="w-80 bg-gray-800 p-4 rounded shadow-lg border border-gray-700 flex flex-col">
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
                    <div className="text-sm text-gray-400">Ciudad</div>
                    <div className="font-bold text-lg text-white">{selectedTile.city_name}</div>
                    <div className="text-xs text-yellow-500">{selectedTile.points} puntos</div>
                  </div>
                  
                  <div>
                    <div className="text-sm text-gray-400">Jugador</div>
                    <div className="font-bold text-white">{selectedTile.owner_name || 'Bárbaros'}</div>
                  </div>

                  {selectedTile.alliance_name && (
                    <div>
                      <div className="text-sm text-gray-400">Alianza</div>
                      <div className="font-bold text-blue-400">[{selectedTile.alliance_name}]</div>
                    </div>
                  )}

                  <div className="divider"></div>

                  {currentCity && selectedTile.city_id !== currentCity.id && (
                    <div className="grid grid-cols-2 gap-2">
                      <button 
                        className="btn btn-sm btn-error w-full"
                        onClick={() => navigate(`/send-movement/${selectedTile.city_id}`)}
                      >
                        Atacar
                      </button>
                      <button className="btn btn-sm btn-info w-full">Espiar</button>
                      <button className="btn btn-sm btn-success w-full">Comerciar</button>
                      <button className="btn btn-sm btn-warning w-full">Mensaje</button>
                    </div>
                  )}
                </div>
              ) : selectedTile.oasis_id ? (
                <div className="space-y-3">
                    <div>
                        <div className="text-sm text-gray-400">Oasis</div>
                        <div className="font-bold text-lg text-white capitalize">{selectedTile.resource_type} (+{selectedTile.bonus_percent}%)</div>
                    </div>
                    <div>
                        <div className="text-sm text-gray-400">Estado</div>
                        <div className="font-bold text-white">{selectedTile.is_conquered ? (selectedTile.owner_id ? 'Conquistado' : 'Ocupado') : 'Salvaje'}</div>
                    </div>
                     {currentCity && (
                    <div className="grid grid-cols-2 gap-2">
                      <button 
                        className="btn btn-sm btn-error w-full"
                        onClick={() => navigate(`/send-movement/${selectedTile.oasis_id}?type=oasis`)}
                      >
                        Atacar
                      </button>
                      <button className="btn btn-sm btn-info w-full">Espiar</button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-gray-500 italic mt-4">
                  Terreno salvaje. No hay asentamientos aquí.
                </div>
              )}
            </div>
          ) : (
            <div className="text-gray-500 text-center mt-10">
              Selecciona una casilla en el mapa para ver información.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MapView;
