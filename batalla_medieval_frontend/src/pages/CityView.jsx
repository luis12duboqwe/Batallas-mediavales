import { useEffect } from 'react';
import { useCityStore } from '../store/cityStore';
import { buildingList } from '../utils/gameMath';

const CityView = () => {
  const { buildings, loadCity } = useCityStore();

  useEffect(() => {
    loadCity().catch(() => {});
  }, [loadCity]);

  const buildingMap = buildingList.map((name) => buildings.find((b) => b.name === name) || { name, level: 0 });

  return (
    <div>
      <h2 className="text-2xl mb-4">Vista de la ciudad</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {buildingMap.map((b) => (
          <div key={b.name} className="card p-4 text-center">
            <div className="h-16 w-16 rounded-full bg-gray-800 mx-auto mb-3 border border-yellow-800/50 flex items-center justify-center text-2xl">
              🏰
            </div>
            <h3 className="text-lg">{b.name}</h3>
            <p className="text-sm text-gray-400">Nivel {b.level}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default CityView;
