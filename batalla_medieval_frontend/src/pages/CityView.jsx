import { useEffect } from 'react';
import { useCityStore } from '../store/cityStore';
import { buildingList } from '../utils/gameMath';

const CityView = () => {
  const { buildings, loadCity } = useCityStore();

  useEffect(() => {
    loadCity().catch(() => {});
  }, [loadCity]);

  const buildingMap = buildingList.map((name) => buildings.find((b) => b.name === name) || { name, level: 0 });

  const buildingIcons = {
    Ayuntamiento: '🏛️',
    Cuartel: '🛡️',
    Mina: '⛏️',
    Aserradero: '🪵',
    Ladrillar: '🧱',
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl">Vista de la ciudad</h2>
          <p className="text-gray-400">Malla detallada de tus estructuras</p>
        </div>
        <span className="badge">Estado en tiempo real</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {buildingMap.map((b) => (
          <div
            key={b.name}
            className="card relative p-4 text-center overflow-hidden group transition hover:-translate-y-1 hover:shadow-[0_16px_40px_rgba(0,0,0,0.45)]"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-yellow-400/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition" />
            <div className="h-16 w-16 rounded-full bg-gray-800/80 mx-auto mb-3 border border-yellow-800/50 flex items-center justify-center text-2xl shadow-inner">
              {buildingIcons[b.name] || '🏰'}
            </div>
            <h3 className="text-lg">{b.name}</h3>
            <p className="text-sm text-gray-400">Nivel {b.level}</p>
            <div className="floating-panel">
              <span className="text-yellow-200">Coste</span>
              <span className="text-[11px] text-gray-200">Mejora en progreso</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default CityView;
