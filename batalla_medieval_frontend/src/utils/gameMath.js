const RESOURCE_FIELDS = ['wood', 'stone', 'iron', 'gold'];

export const calculateProduction = (resources, productionRates, seconds) => {
  const updated = { ...resources };
  RESOURCE_FIELDS.forEach((resource) => {
    updated[resource] = (updated[resource] || 0) + (productionRates[resource] || 0) * (seconds / 3600);
  });
  updated.population = Math.min(updated.population, updated.populationMax || updated.population);
  return updated;
};

export const TROOP_TYPES = {
  basic_infantry: 'Lancero Común',
  heavy_infantry: 'Soldado de Acero',
  archer: 'Arquero Real',
  fast_cavalry: 'Jinete Explorador',
  heavy_cavalry: 'Caballero Imperial',
  spy: 'Infiltrador',
  ram: 'Quebramuros',
  catapult: 'Tormenta de Piedra',
  noble: 'Noble',
};

export const troopList = Object.keys(TROOP_TYPES);

export const buildingList = [
  'town_hall',
  'barracks',
  'stable',
  'wall',
  'market',
  'farm',
  'warehouse',
  'smithy',
  'workshop',
  'church',
  'cathedral',
  'world_wonder',
];
