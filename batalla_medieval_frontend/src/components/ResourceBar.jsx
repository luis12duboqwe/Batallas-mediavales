import { useEffect } from 'react';
import { useCityStore } from '../store/cityStore';
import { formatNumber } from '../utils/format';

const ResourceItem = ({ label, value, icon }) => (
  <div className="flex items-center gap-2 bg-gray-900/70 px-3 py-1 rounded border border-yellow-800/40 shadow-sm">
    <span className="text-yellow-400">{icon}</span>
    <span className="text-sm text-gray-300">{label}</span>
    <span className="font-semibold">{formatNumber(value)}</span>
  </div>
);

const ResourceBar = () => {
  const { resources, tickResources } = useCityStore();

  useEffect(() => {
    const interval = setInterval(() => tickResources(1), 1000);
    return () => clearInterval(interval);
  }, [tickResources]);

  return (
    <div className="sticky top-0 z-30 bg-gray-950/90 backdrop-blur border-b border-yellow-800/40 px-6 py-2 flex items-center gap-3 overflow-x-auto">
      <ResourceItem label="Madera" value={resources.wood} icon="🪵" />
      <ResourceItem label="Ladrillo" value={resources.clay} icon="🧱" />
      <ResourceItem label="Hierro" value={resources.iron} icon="⛓️" />
      <ResourceItem label="Población" value={`${formatNumber(resources.population)}/${formatNumber(resources.populationMax)}`} icon="👥" />
    </div>
  );
};

export default ResourceBar;
