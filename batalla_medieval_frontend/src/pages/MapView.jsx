import { useState } from 'react';
import { useGameStore } from '../store/gameStore';

const MapView = () => {
  const { selectedTile, setSelectedTile, mapCenter, setMapCenter } = useGameStore();
  const [size] = useState(9);

  const cells = [];
  for (let y = mapCenter.y - Math.floor(size / 2); y <= mapCenter.y + Math.floor(size / 2); y += 1) {
    for (let x = mapCenter.x - Math.floor(size / 2); x <= mapCenter.x + Math.floor(size / 2); x += 1) {
      cells.push({ x, y });
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Mapa del mundo</h1>
          <p className="text-gray-400">Explora las coordenadas y selecciona objetivos</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={() => setMapCenter({ x: mapCenter.x, y: mapCenter.y - 1 })}>↑</button>
          <button className="btn-primary" onClick={() => setMapCenter({ x: mapCenter.x - 1, y: mapCenter.y })}>←</button>
          <button className="btn-primary" onClick={() => setMapCenter({ x: mapCenter.x + 1, y: mapCenter.y })}>→</button>
          <button className="btn-primary" onClick={() => setMapCenter({ x: mapCenter.x, y: mapCenter.y + 1 })}>↓</button>
        </div>
      </div>
      <div className="grid grid-cols-9 gap-2">
        {cells.map((cell) => (
          <button
            key={`${cell.x}-${cell.y}`}
            className={`aspect-square rounded border ${
              selectedTile?.x === cell.x && selectedTile?.y === cell.y
                ? 'border-yellow-400 bg-yellow-500/20'
                : 'border-gray-800 bg-gray-900'
            }`}
            onClick={() => setSelectedTile(cell)}
          >
            <span className="text-xs text-gray-400">{cell.x},{cell.y}</span>
          </button>
        ))}
      </div>
      {selectedTile && (
        <div className="card p-4">
          <h2 className="text-xl">Coordenada {selectedTile.x},{selectedTile.y}</h2>
          <p className="text-gray-400">Selecciona para ver información y acciones disponibles.</p>
          <div className="flex gap-2 mt-3">
            <button className="btn-primary">Atacar</button>
            <button className="btn-primary bg-gray-800 text-yellow-300">Espiar</button>
            <button className="btn-primary bg-gray-800 text-yellow-300">Reforzar</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default MapView;
