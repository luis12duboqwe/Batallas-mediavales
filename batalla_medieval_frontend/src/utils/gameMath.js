export const calculateProduction = (resources, productionRates, seconds) => {
  const updated = { ...resources };
  updated.wood += (productionRates.wood || 0) * (seconds / 3600);
  updated.clay += (productionRates.clay || 0) * (seconds / 3600);
  updated.iron += (productionRates.iron || 0) * (seconds / 3600);
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
  'Casa Central',
  'Aserradero',
  'Cantera de Ladrillo',
  'Mina Profunda',
  'Hacienda',
  'Gran Depósito',
  'Barracas',
  'Establos Imperiales',
  'Forja Bélica',
  'Muralla de Guardia',
  'Plaza Comercial',
  'Comandancia Militar',
];
