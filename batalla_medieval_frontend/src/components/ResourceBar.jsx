import { useEffect } from 'react';
import { useCityStore } from '../store/cityStore';
import { formatNumber } from '../utils/format';

const ResourceItem = ({ label, value, icon, tip }) => (
  <div
    className="flex items-center gap-2 bg-gradient-to-r from-gray-900/80 via-gray-900/40 to-gray-900/70 px-3 py-1.5 rounded-lg border border-yellow-800/40 shadow-inner backdrop-blur tooltip"
    data-tip={tip}
  >
    <span className="text-yellow-400 drop-shadow">{icon}</span>
    <span className="text-xs uppercase tracking-wide text-gray-300">{label}</span>
    <span className="font-semibold text-sm">{formatNumber(value)}</span>
  </div>
);

const ResourceBar = () => {
  const { resources, tickResources } = useCityStore();

  useEffect(() => {
    const interval = setInterval(() => tickResources(1), 1000);
    return () => clearInterval(interval);
  }, [tickResources]);

  return (
    <div className="sticky top-[52px] z-30 bg-gray-950/90 backdrop-blur border-b border-yellow-800/30 px-6 py-2 flex items-center gap-3 overflow-x-auto shadow-[0_12px_40px_rgba(0,0,0,0.35)]">
      <ResourceItem label="Madera" value={resources.wood} icon="🪵" tip="Recurso producido por Aserradero" />
      <ResourceItem label="Ladrillo" value={resources.clay} icon="🧱" tip="Recurso producido por Ladrillar" />
      <ResourceItem label="Hierro" value={resources.iron} icon="⛓️" tip="Recurso producido por Mina" />
      <ResourceItem
        label="Población"
        value={`${formatNumber(resources.population)}/${formatNumber(resources.populationMax)}`}
        icon="👥"
        tip="Población disponible para entrenar"
      />
    </div>
  );
};

export default ResourceBar;
