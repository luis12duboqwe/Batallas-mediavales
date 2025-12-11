export const calculateProduction = (resources, productionRates, seconds) => {
  const updated = { ...resources };
  updated.wood += (productionRates.wood || 0) * (seconds / 3600);
  updated.clay += (productionRates.clay || 0) * (seconds / 3600);
  updated.iron += (productionRates.iron || 0) * (seconds / 3600);
  updated.population = Math.min(updated.population, updated.populationMax || updated.population);
  return updated;
};

export const troopList = [
  'Lancero Común',
  'Soldado de Acero',
  'Arquero Real',
  'Jinete Explorador',
  'Caballero Imperial',
  'Infiltrador',
  'Quebramuros',
  'Tormenta de Piedra',
];

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
