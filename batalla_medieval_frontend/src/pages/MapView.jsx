import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/axiosClient';
import { useUserStore } from '../store/userStore';
import { useCityStore } from '../store/cityStore';
import { useNavigate } from 'react-router-dom';
import GameIcon from '../components/GameIcon';
import MapTile, { OASIS_RESOURCE_META } from '../components/parallel-map/MapTile';
import { readMapTilesResponse } from '../utils/collectionResponse';

const RADIUS = 7;
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
  const user = useUserStore((state) => state.user);
  const currentCity = useCityStore((state) => state.currentCity);
  const navigate = useNavigate();
  const [center, setCenter] = useState({ x: 0, y: 0 });
  const [tiles, setTiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [selectedTile, setSelectedTile] = useState(null);
  const [focusedTileKey, setFocusedTileKey] = useState(null);
  const [jumpCoords, setJumpCoords] = useState({ x: 0, y: 0 });
  const [jumpError, setJumpError] = useState('');
  const mapGridRef = useRef(null);
  const worldId = user?.world_id;
  const loadedWorldRef = useRef(worldId);

  // A fresh city selection changes the origin. Resource refreshes of the same
  // city must not snap the player's manually explored map back to home.
  useEffect(() => {
    if (!currentCity) return;
    const x = currentCity.x ?? 0;
    const y = currentCity.y ?? 0;
    setCenter((previous) => previous.x === x && previous.y === y ? previous : { x, y });
    setJumpCoords({ x, y });
    setJumpError('');
    setSelectedTile(null);
    setFocusedTileKey(null);
  }, [currentCity?.id, currentCity?.world_id, currentCity?.x, currentCity?.y]);

  useEffect(() => {
    let active = true;
    if (loadedWorldRef.current !== worldId) {
      loadedWorldRef.current = worldId;
      setTiles([]);
      setSelectedTile(null);
      setFocusedTileKey(null);
    }
    if (!worldId) {
      setTiles([]);
      setSelectedTile(null);
      setLoading(false);
      setLoadError(false);
      return () => { active = false; };
    }
    setLoading(true);
    setLoadError(false);
    api.getMapTiles(worldId, center.x, center.y, RADIUS)
      .then(({ data }) => {
        if (!active) return;
        const nextTiles = readMapTilesResponse(data);
        setTiles(nextTiles);
        // Keep selection only while its coordinate remains visible, and refresh
        // the details from the authoritative response rather than a stale tile.
        setSelectedTile((previous) => previous
          ? nextTiles.find((tile) => tile.x === previous.x && tile.y === previous.y) || null
          : null);
      })
      .catch((error) => {
        if (active) {
          console.error('Failed to load map', error);
          setTiles([]);
          setSelectedTile(null);
          setLoadError(true);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [center.x, center.y, worldId, retryKey]);

  const handleJump = (event) => {
    event.preventDefault();
    const parseCoordinate = (value) => {
      const text = String(value).trim();
      if (!/^\\d+$/.test(text)) return null;
      const number = Number(text);
      return Number.isSafeInteger(number) ? number : null;
    };
    const x = parseCoordinate(jumpCoords.x);
    const y = parseCoordinate(jumpCoords.y);
    if (x === null || y === null) {
      setJumpError('Introduce coordenadas X e Y enteras, no negativas y válidas.');
      return;
    }
    setJumpError('');
    setCenter((previous) => previous.x === x && previous.y === y ? previous : { x, y });
  };

  const handleMove = useCallback((dx, dy) => {
    setCenter((previous) => {
      const x = Math.max(0, previous.x + dx);
      const y = Math.max(0, previous.y + dy);
      return x === previous.x && y === previous.y ? previous : { x, y };
    });
  }, []);

  const handleTileSelect = useCallback((tile) => setSelectedTile(tile), []);
  const handleTileFocus = useCallback((tile) => {
    const key = `${tile.x},${tile.y}`;
    setFocusedTileKey((previous) => previous === key ? previous : key);
  }, []);

  // Only rebuild the grid when tile data changes, not on selection or form edits.
  const mapRows = useMemo(() => {
    const byRow = new Map();
    for (const tile of tiles) {
      if (!byRow.has(tile.y)) byRow.set(tile.y, []);
      byRow.get(tile.y).push(tile);
    }
    return [...byRow.entries()]
      .sort(([a], [b]) => b - a)
      .map(([y, rowTiles]) => [y, rowTiles.sort((a, b) => a.x - b.x)]);
  }, [tiles]);
  const tileByKey = useMemo(() => new Map(tiles.map((tile) => [`${tile.x},${tile.y}`, tile])), [tiles]);
  const centerKey = `${center.x},${center.y}`;
  const firstTile = mapRows[0]?.[1]?.[0];
  const tabStopKey = focusedTileKey && tileByKey.has(focusedTileKey)
    ? focusedTileKey
    : tileByKey.has(centerKey) ? centerKey : firstTile ? `${firstTile.x},${firstTile.y}` : null;

  const handleTileNavigate = useCallback((event, tile) => {
    const { key, ctrlKey, metaKey } = event;
    let next = null;
    if (key === 'ArrowLeft') next = tileByKey.get(`${tile.x - 1},${tile.y}`);
    else if (key === 'ArrowRight') next = tileByKey.get(`${tile.x + 1},${tile.y}`);
    else if (key === 'ArrowUp') next = tileByKey.get(`${tile.x},${tile.y + 1}`);
    else if (key === 'ArrowDown') next = tileByKey.get(`${tile.x},${tile.y - 1}`);
    else if (key === 'Home' || key === 'End') {
      const row = (ctrlKey || metaKey)
        ? (key === 'Home' ? mapRows[0]?.[1] : mapRows[mapRows.length - 1]?.[1])
        : mapRows.find(([y]) => y === tile.y)?.[1];
      next = key === 'Home' ? row?.[0] : row?.[row.length - 1];
    } else return;

    event.preventDefault();
    if (!next) return;
    const target = mapGridRef.current?.querySelector(
      `[data-map-coordinate="${next.x},${next.y}"]`
    );
    target?.focus();
  }, [mapRows, tileByKey]);

  const selectedOasisResource = selectedTile?.oasis_id ? OASIS_RESOURCE_META[selectedTile.resource_type] : null;
  const selectedSettlementLabel = selectedTile?.settlement_type === 'camp' ? 'Campamento' : 'Ciudad';
  const selectedSettlementIsMine = Boolean(user?.id && selectedTile?.owner_id === user.id);
  const canSendFromCity = Boolean(currentCity && currentCity.world_id === worldId);

  return (
    <div className="p-2 sm:p-4 h-full flex flex-col min-w-0">
      <div className="flex flex-col gap-3 mb-4 bg-black/40 p-4 rounded sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-amber-500">Mapa Global</h1>
          <p className="text-xs text-gray-300" data-testid="map-center" aria-live="polite">
            Centro: ({center.x}, {center.y})
          </p>
        </div>
        <form noValidate onSubmit={handleJump} className="grid w-full grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-2 sm:w-auto" aria-label="Ir a coordenadas">
          <input type="number" step="1" min="0" inputMode="numeric" aria-label="Coordenada X" aria-invalid={Boolean(jumpError)} aria-describedby={jumpError ? 'map-jump-error' : undefined} className="input input-sm min-w-0 w-full bg-black/50" placeholder="X" value={jumpCoords.x} onChange={(event) => { setJumpCoords((previous) => ({ ...previous, x: event.target.value })); setJumpError(''); }} />
          <input type="number" step="1" min="0" inputMode="numeric" aria-label="Coordenada Y" aria-invalid={Boolean(jumpError)} aria-describedby={jumpError ? 'map-jump-error' : undefined} className="input input-sm min-w-0 w-full bg-black/50" placeholder="Y" value={jumpCoords.y} onChange={(event) => { setJumpCoords((previous) => ({ ...previous, y: event.target.value })); setJumpError(''); }} />
          <button type="submit" className="btn btn-sm btn-primary">Ir</button>
          {jumpError && <p id="map-jump-error" role="alert" className="col-span-3 text-xs text-red-200">{jumpError}</p>}
        </form>
      </div>

      <div className="flex flex-1 min-w-0 flex-col gap-4 lg:flex-row lg:overflow-hidden">
        <div className="min-h-[28rem] min-w-0 flex-1 relative bg-gray-900 rounded overflow-auto p-4" data-testid="map-grid-panel" aria-busy={loading}>
          {loading && <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20" role="status">Cargando...</div>}
          {loadError && !loading && (
            <div role="alert" data-testid="map-load-error" className="rounded border border-red-700 bg-red-950/60 p-4 text-sm text-red-100">
              <p>No se pudo cargar el mapa. La vista se recuperará al reintentar.</p>
              <button type="button" className="btn-primary mt-3" onClick={() => setRetryKey((value) => value + 1)}>Reintentar mapa</button>
            </div>
          )}
          {!loading && !loadError && tiles.length === 0 && (
            <div role="status" data-testid="map-empty" className="p-4 text-center text-gray-300">
              No hay casillas disponibles en esta zona.
            </div>
          )}
          {!loadError && <div className="relative w-max mx-auto p-10" data-testid="map-grid-content">
            <button type="button" aria-label="Mover mapa hacia arriba" onClick={() => handleMove(0, 5)} className="absolute top-2 left-1/2 -translate-x-1/2 btn btn-xs btn-circle"><GameIcon name="arrowUp" size={18} /></button>
            <button type="button" aria-label="Mover mapa hacia abajo" onClick={() => handleMove(0, -5)} className="absolute bottom-2 left-1/2 -translate-x-1/2 btn btn-xs btn-circle"><GameIcon name="arrowDown" size={18} /></button>
            <button type="button" aria-label="Mover mapa hacia la izquierda" onClick={() => handleMove(-5, 0)} className="absolute left-2 top-1/2 -translate-y-1/2 btn btn-xs btn-circle"><GameIcon name="arrowLeft" size={18} /></button>
            <button type="button" aria-label="Mover mapa hacia la derecha" onClick={() => handleMove(5, 0)} className="absolute right-2 top-1/2 -translate-y-1/2 btn btn-xs btn-circle"><GameIcon name="arrowRight" size={18} /></button>
            <p id="map-keyboard-help" className="sr-only">Usa las flechas para moverte entre casillas. Inicio y Fin navegan por la fila; Control más Inicio o Fin va a los extremos del mapa. Enter o Espacio selecciona una casilla.</p>
            <div ref={mapGridRef} className="grid gap-0.5 bg-black/50 p-1" role="group" aria-label="Cuadrícula del mapa" aria-describedby="map-keyboard-help">
              {mapRows.map(([y, rowTiles]) => (
                <div key={y} className="flex gap-0.5">
                  {rowTiles.map((tile) => (
                    <MapTile
                      key={`${tile.x},${tile.y}`}
                      tile={tile}
                      isCenter={tile.x === center.x && tile.y === center.y}
                      isSelected={Boolean(selectedTile && selectedTile.x === tile.x && selectedTile.y === tile.y)}
                      isMine={Boolean(user?.id && tile.owner_id === user.id)}
                      isTabStop={tabStopKey === `${tile.x},${tile.y}`}
                      onSelect={handleTileSelect}
                      onFocusTile={handleTileFocus}
                      onNavigate={handleTileNavigate}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>}
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
                  {canSendFromCity && !selectedSettlementIsMine && (
                    <div className="grid grid-cols-2 gap-2">
                      <button type="button" disabled={loading} className="btn btn-sm btn-error w-full" onClick={() => navigate(`/send-movement/${selectedTile.city_id}`)}>Atacar</button>
                      <button type="button" disabled title="Selecciona Espionaje en el formulario de Enviar Tropas." className="btn btn-sm btn-info w-full">Espiar</button>
                      <button type="button" disabled title="Utiliza la sección Mercado para comerciar." className="btn btn-sm btn-success w-full">Comerciar</button>
                      <button type="button" disabled title="Utiliza la sección Mensajes para contactar jugadores." className="btn btn-sm btn-warning w-full">Mensaje</button>
                    </div>
                  )}
                </div>
              ) : selectedTile.oasis_id ? (
                <div className="space-y-3">
                  <div><div className="text-sm text-gray-400">Oasis</div><div className="font-bold text-lg text-white flex items-center gap-2"><GameIcon name={selectedOasisResource?.icon || 'oasis'} size={20} />{selectedOasisResource?.label || selectedTile.resource_type} (+{selectedTile.bonus_percent}%)</div></div>
                  <PveDifficulty tile={selectedTile} />
                  <div><div className="text-sm text-gray-400">Estado</div><div className="font-bold text-white">{selectedTile.is_conquered ? (selectedTile.owner_id ? 'Conquistado' : 'Ocupado') : 'Salvaje'}</div></div>
                  {canSendFromCity && <div className="grid grid-cols-2 gap-2"><button type="button" disabled={loading} className="btn btn-sm btn-error w-full" onClick={() => navigate(`/send-movement/${selectedTile.oasis_id}?type=oasis`)}>Atacar</button><button type="button" disabled title="Los oasis se atacan desde el formulario de movimiento." className="btn btn-sm btn-info w-full">Espiar</button></div>}
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
