import { useEffect, useMemo, useRef, useState } from 'react';
import MapCell from './MapCell';

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const MapGrid = ({
  gridSize = 50,
  zoom,
  onZoomChange,
  center,
  onCenterChange,
  cities,
  filter,
  selected,
  onCellClick,
}) => {
  const containerRef = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [origin, setOrigin] = useState({ x: Math.max(0, center.x - 5), y: Math.max(0, center.y - 5) });
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0, originX: 0, originY: 0 });

  const cellSize = useMemo(() => 36 * zoom, [zoom]);

  useEffect(() => {
    const updateSize = () => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (rect) {
        setSize({ width: rect.width, height: rect.height });
      }
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  const colsVisible = Math.max(1, Math.ceil(size.width / cellSize) + 2);
  const rowsVisible = Math.max(1, Math.ceil(size.height / cellSize) + 2);

  const clampOrigin = (nextOrigin) => {
    const maxX = Math.max(0, gridSize - colsVisible);
    const maxY = Math.max(0, gridSize - rowsVisible);
    return {
      x: clamp(nextOrigin.x, 0, maxX),
      y: clamp(nextOrigin.y, 0, maxY),
    };
  };

  useEffect(() => {
    setOrigin((prev) => {
      const next = clampOrigin({
        x: center.x - colsVisible / 2,
        y: center.y - rowsVisible / 2,
      });
      return { ...prev, ...next };
    });
  }, [center.x, center.y, colsVisible, rowsVisible]);

  useEffect(() => {
    const newCenter = {
      x: origin.x + colsVisible / 2,
      y: origin.y + rowsVisible / 2,
    };
    onCenterChange?.({ x: Math.round(newCenter.x), y: Math.round(newCenter.y) });
  }, [origin.x, origin.y, colsVisible, rowsVisible, onCenterChange]);

  const handleWheel = (event) => {
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.1 : 0.1;
    const nextZoom = clamp(zoom + delta, 0.5, 3);
    onZoomChange?.(Number(nextZoom.toFixed(2)));
  };

  const handleMouseDown = (event) => {
    setDragging(true);
    dragStart.current = {
      x: event.clientX,
      y: event.clientY,
      originX: origin.x,
      originY: origin.y,
    };
  };

  const handleMouseMove = (event) => {
    if (!dragging) return;
    const dx = event.clientX - dragStart.current.x;
    const dy = event.clientY - dragStart.current.y;
    const deltaCells = {
      x: dx / cellSize,
      y: dy / cellSize,
    };
    setOrigin(clampOrigin({
      x: dragStart.current.originX - deltaCells.x,
      y: dragStart.current.originY - deltaCells.y,
    }));
  };

  const handleMouseUp = () => setDragging(false);

  useEffect(() => {
    if (!dragging) return;
    const handleLeave = () => setDragging(false);
    window.addEventListener('mouseup', handleLeave);
    window.addEventListener('mouseleave', handleLeave);
    return () => {
      window.removeEventListener('mouseup', handleLeave);
      window.removeEventListener('mouseleave', handleLeave);
    };
  }, [dragging]);

  const startX = Math.max(0, Math.floor(origin.x));
  const startY = Math.max(0, Math.floor(origin.y));
  const endX = Math.min(gridSize - 1, Math.ceil(origin.x + colsVisible));
  const endY = Math.min(gridSize - 1, Math.ceil(origin.y + rowsVisible));

  const offsetX = -(origin.x - startX) * cellSize;
  const offsetY = -(origin.y - startY) * cellSize;

  const visibleCities = useMemo(() => {
    const filtered = filter === 'all'
      ? cities
      : cities.filter((city) => city.relation === filter || (filter === 'own' && city.isOwn));
    return filtered.filter((city) => city.x >= startX && city.x <= endX && city.y >= startY && city.y <= endY);
  }, [cities, endX, filter, startX, endY, startY]);

  const cityKey = (x, y) => `${x}-${y}`;
  const cityMap = useMemo(() => {
    const map = new Map();
    visibleCities.forEach((city) => {
      map.set(cityKey(city.x, city.y), city);
    });
    return map;
  }, [visibleCities]);

  const cells = [];
  for (let y = startY; y <= endY; y += 1) {
    for (let x = startX; x <= endX; x += 1) {
      cells.push({ x, y, city: cityMap.get(cityKey(x, y)) });
    }
  }

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden rounded-lg border border-yellow-800/40 bg-gradient-to-br from-gray-950 to-gray-900"
      onWheel={handleWheel}
      onMouseMove={handleMouseMove}
      onMouseDown={handleMouseDown}
      onMouseUp={handleMouseUp}
    >
      <div
        className="absolute"
        style={{
          width: (endX - startX + 1) * cellSize,
          height: (endY - startY + 1) * cellSize,
          transform: `translate(${offsetX}px, ${offsetY}px)`,
        }}
      >
        {cells.map((cell) => (
          <MapCell
            key={`${cell.x}-${cell.y}`}
            x={cell.x - startX}
            y={cell.y - startY}
            size={cellSize}
            city={cell.city}
            selected={selected?.x === cell.x && selected?.y === cell.y}
            onClick={({ city }) => onCellClick({ x: cell.x, y: cell.y, city })}
          />
        ))}
      </div>
    </div>
  );
};

export default MapGrid;
