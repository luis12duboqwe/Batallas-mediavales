import { useEffect, useMemo, useRef, useState } from 'react';
import MapCell from './MapCell';

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
const BASE_CELL_SIZE = 40;

const MapGrid = ({
  gridSize = 20,
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
  const cellSize = useMemo(() => BASE_CELL_SIZE, []);

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
    const rounded = { x: Math.round(newCenter.x), y: Math.round(newCenter.y) };
    onCenterChange?.((prev) => {
      if (prev?.x === rounded.x && prev?.y === rounded.y) return prev;
      return rounded;
    });
  }, [origin.x, origin.y, colsVisible, rowsVisible, onCenterChange]);

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

  const cells = useMemo(() => {
    const batch = [];
    for (let y = startY; y <= endY; y += 1) {
      for (let x = startX; x <= endX; x += 1) {
        batch.push({ x, y, city: cityMap.get(cityKey(x, y)) });
      }
    }
    return batch;
  }, [cityMap, endX, endY, startX, startY]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden rounded-xl border border-amber-900/60 bg-[radial-gradient(circle_at_top,_#0f2f1f,_#0b1d14_45%,_#0a1812)]"
    >
      <div className="absolute inset-0 pointer-events-none bg-[linear-gradient(rgba(84,62,34,0.18)_1px,transparent_1px),linear-gradient(90deg,rgba(84,62,34,0.18)_1px,transparent_1px)] bg-[size:40px_40px]" />
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
