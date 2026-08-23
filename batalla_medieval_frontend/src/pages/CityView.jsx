import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useCityStore } from '../store/cityStore';
import { buildingList } from '../utils/gameMath';

const oasisResourceMeta = {
  wood: { icon: '🌲', label: 'Madera' },
  stone: { icon: '🪨', label: 'Piedra' },
  iron: { icon: '⛓️', label: 'Hierro' },
  gold: { icon: '🪙', label: 'Oro' },
};

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

const CityView = () => {
  const { t } = useTranslation();
  const { buildings, loadCity, currentCity } = useCityStore();

  useEffect(() => {
    loadCity().catch(() => {});
  }, [loadCity]);

  const availableNames = new Set(buildings.map((building) => building.name));
  const visibleCatalog = currentCity?.settlement_type === 'camp'
    ? buildingList.filter((name) => availableNames.has(name))
    : buildingList;
  const buildingMap = visibleCatalog.map(
    (name) => buildings.find((building) => building.name === name) || { name, level: 0 },
  );
  const isCamp = currentCity?.settlement_type === 'camp';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl">{isCamp ? 'Vista del campamento' : 'Vista de la ciudad'}</h2>
          <p className="text-gray-400">
            {isCamp
              ? 'Asentamiento logístico con producción y capacidad reducidas.'
              : 'Malla detallada de tus estructuras.'}
          </p>
        </div>
        <span className="badge">{isCamp ? '⛺ Campamento' : '🏰 Ciudad'} · Estado en tiempo real</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {buildingMap.map((building) => (
          <div
            key={building.name}
            className="card relative p-4 text-center overflow-hidden group transition hover:-translate-y-1 hover:shadow-[0_16px_40px_rgba(0,0,0,0.45)]"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-yellow-400/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition" />
            <div className="h-16 w-16 rounded-full bg-gray-800/80 mx-auto mb-3 border border-yellow-800/50 flex items-center justify-center text-2xl shadow-inner">
              {buildingIcons[building.name] || '🏰'}
            </div>
            <h3 className="text-lg">{building.display_name || t(building.name)}</h3>
            <p className="text-sm text-gray-400">Nivel {building.level}</p>
            <div className="floating-panel">
              <span className="text-yellow-200">Estructura</span>
              <span className="text-[11px] text-gray-200">{building.level > 0 ? 'Construida' : 'Disponible'}</span>
            </div>
          </div>
        ))}
      </div>

      {currentCity?.oases && currentCity.oases.length > 0 && (
        <div className="mt-8 border-t border-gray-700 pt-6">
          <h2 className="text-xl font-bold text-amber-500 mb-4">Oasis Conquistados</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {currentCity.oases.map((oasis) => {
              const resourceMeta = oasisResourceMeta[oasis.resource_type] || {
                icon: '🏞️',
                label: oasis.resource_type,
              };
              return (
                <div key={oasis.id} className="bg-gray-800 p-4 rounded border border-green-700/50 shadow-lg relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-1 bg-green-900/50 rounded-bl text-xs text-green-200">
                    Activo
                  </div>
                  <div className="flex items-center gap-3 mb-2">
                    <div className="text-3xl filter drop-shadow-lg">{resourceMeta.icon}</div>
                    <div>
                      <div className="font-bold text-white text-lg">{resourceMeta.label}</div>
                      <div className="text-green-400 font-bold text-sm">+{oasis.bonus_percent}% Producción</div>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 mt-2 flex justify-between">
                    <span>Coordenadas:</span>
                    <span className="font-mono text-gray-300">({oasis.x}, {oasis.y})</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default CityView;
