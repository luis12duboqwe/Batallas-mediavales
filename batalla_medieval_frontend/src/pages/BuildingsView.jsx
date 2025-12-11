import { useEffect } from 'react';
import BuildingCard from '../components/BuildingCard';
import { useCityStore } from '../store/cityStore';

const BuildingsView = () => {
  const { buildings, loadCity, upgrade } = useCityStore();

  useEffect(() => {
    loadCity().catch(() => {});
  }, [loadCity]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Edificios</h1>
          <p className="text-gray-400">Gestiona las mejoras de tu ciudad</p>
        </div>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {buildings.map((b) => (
          <BuildingCard key={b.name} building={b} onUpgrade={upgrade} />
        ))}
      </div>
    </div>
  );
};

export default BuildingsView;
