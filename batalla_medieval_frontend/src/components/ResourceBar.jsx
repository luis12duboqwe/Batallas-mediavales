import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useCityStore } from '../store/cityStore';
import { formatNumber } from '../utils/format';

const ResourceItem = ({ label, value, icon, tip }) => (
  <div
    className="flex shrink-0 items-center gap-2 bg-gradient-to-r from-gray-900/80 via-gray-900/40 to-gray-900/70 px-3 py-1.5 rounded-lg border border-yellow-800/40 shadow-inner backdrop-blur tooltip"
    data-tip={tip}
    aria-label={`${label}: ${value}. ${tip}`}
  >
    <span className="text-yellow-400 drop-shadow" aria-hidden>{icon}</span>
    <span className="text-xs uppercase tracking-wide text-gray-300">{label}</span>
    <span className="font-semibold text-sm">{value}</span>
  </div>
);

const ResourceBar = () => {
  const { t } = useTranslation();
  const { resources, storageLimit, militaryEconomy, tickResources } = useCityStore();

  useEffect(() => {
    const interval = setInterval(() => tickResources(1), 1000);
    return () => clearInterval(interval);
  }, [tickResources]);

  const upkeepCommitted = militaryEconomy.upkeepUsedPerHour + militaryEconomy.upkeepReservedPerHour;
  const upkeepTip = t('resources.upkeep_tip', {
    used: militaryEconomy.upkeepUsedPerHour.toFixed(2),
    reserved: militaryEconomy.upkeepReservedPerHour.toFixed(2),
    net: militaryEconomy.netGoldPerHour.toFixed(2),
  });

  return (
    <div
      className="sticky top-[60px] sm:top-[68px] z-30 bg-gray-950/90 backdrop-blur border-b border-yellow-800/30 px-3 sm:px-6 py-2 flex items-center gap-3 overflow-x-auto shadow-[0_12px_40px_rgba(0,0,0,0.35)]"
      aria-label={t('resources.summary')}
      data-testid="resource-bar"
    >
      <ResourceItem
        label={t('resources.wood')}
        value={`${formatNumber(resources.wood)}/${formatNumber(storageLimit)}`}
        icon="🪵"
        tip={t('resources.wood_tip')}
      />
      <ResourceItem
        label={t('resources.stone')}
        value={`${formatNumber(resources.stone)}/${formatNumber(storageLimit)}`}
        icon="🪨"
        tip={t('resources.stone_tip')}
      />
      <ResourceItem
        label={t('resources.iron')}
        value={`${formatNumber(resources.iron)}/${formatNumber(storageLimit)}`}
        icon="⛓️"
        tip={t('resources.iron_tip')}
      />
      <ResourceItem
        label={t('resources.gold')}
        value={`${formatNumber(resources.gold)}/${formatNumber(storageLimit)}`}
        icon="🪙"
        tip={t('resources.gold_tip_net', { rate: militaryEconomy.netGoldPerHour.toFixed(2) })}
      />
      <ResourceItem
        label={t('resources.population')}
        value={`${formatNumber(resources.population)}/${formatNumber(resources.populationMax)}`}
        icon="👥"
        tip={t('resources.population_tip')}
      />
      <ResourceItem
        label={t('resources.upkeep')}
        value={`${upkeepCommitted.toFixed(2)}/${militaryEconomy.upkeepCapacityPerHour.toFixed(2)}/h`}
        icon={militaryEconomy.sustainable ? '🛡️' : '⚠️'}
        tip={upkeepTip}
      />
    </div>
  );
};

export default ResourceBar;
