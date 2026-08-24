import { create } from 'zustand';
import { api } from '../api/axiosClient';
import soundManager from '../services/sound';

const RESOURCE_FIELDS = ['wood', 'stone', 'iron', 'gold'];

const movementCategory = (movement, ownedCityIds) => {
  const direction = ownedCityIds.has(movement.origin_city_id) ? 'out' : 'in';
  switch (movement.movement_type) {
    case 'attack':
    case 'spy':
    case 'reinforce':
    case 'transport':
      return `${movement.movement_type}_${direction}`;
    case 'return':
      return 'return';
    default:
      return movement.movement_type || 'other';
  }
};

const normalizeResources = (resources = {}, city = null) => ({
  ...resources,
  population: resources.population_used ?? resources.population ?? 0,
  populationMax:
    resources.population_capacity
    ?? resources.population_max
    ?? resources.populationMax
    ?? city?.population_capacity
    ?? city?.population_max
    ?? 0,
});

const normalizeMilitaryEconomy = (resources = {}) => ({
  upkeepUsedPerHour: Number(resources.upkeep_used_per_hour ?? 0),
  upkeepReservedPerHour: Number(resources.upkeep_reserved_per_hour ?? 0),
  upkeepCapacityPerHour: Number(resources.upkeep_capacity_per_hour ?? 0),
  upkeepAvailablePerHour: Number(resources.upkeep_available_per_hour ?? 0),
  netGoldPerHour: Number(resources.net_gold_per_hour ?? resources.production_per_hour?.gold ?? 0),
  sustainable: resources.upkeep_sustainable ?? true,
});

export const useCityStore = create((set, get) => ({
  currentCity: null,
  cities: [],
  resources: { wood: 0, stone: 0, iron: 0, gold: 0, population: 0, populationMax: 0 },
  storageLimit: 0,
  buildings: [],
  productionRates: { wood: 0, stone: 0, iron: 0, gold: 0 },
  militaryEconomy: normalizeMilitaryEconomy(),
  queues: { buildings: [], research: [], troops: [] },
  movements: [],
  reports: [],
  alliance: null,
  messages: [],
  async loadCity() {
    const { data } = await api.getCity();
    set({
      currentCity: data.city ? { ...data.city } : null,
      cities: data.cities || [],
      resources: normalizeResources(data.resources, data.city),
      storageLimit: data.storage_limit ?? 0,
      buildings: data.buildings,
      productionRates: data.production,
      militaryEconomy: normalizeMilitaryEconomy(data.resources),
      queues: data.queues || { buildings: [], research: [], troops: [] },
    });
    return data;
  },
  tickResources(elapsedSeconds = 1) {
    const { resources, productionRates, storageLimit } = get();
    const updated = { ...resources };
    RESOURCE_FIELDS.forEach(res => {
      const produced = ((productionRates[res] || 0) / 3600) * elapsedSeconds;
      const rawValue = (updated[res] || 0) + produced;
      updated[res] = storageLimit > 0
        ? Math.max(0, Math.min(rawValue, storageLimit))
        : Math.max(0, rawValue);
    });
    set({ resources: updated });
  },
  async upgrade(buildingType) {
    const city = get().currentCity;
    if (!city) return null;
    const { data } = await api.upgradeBuilding({
      cityId: city.id,
      buildingType,
      worldId: city.world_id,
    });
    await get().loadCity();
    return data;
  },
  async cancelBuilding(queueId) {
    await api.cancelBuildingQueue(queueId);
    await get().loadCity();
  },
  async train({ troopType, amount }) {
    const city = get().currentCity;
    if (!city) return null;
    const { data } = await api.trainTroops({
      cityId: city.id,
      troopType,
      amount,
      worldId: city.world_id,
    });
    await get().loadCity();
    return data;
  },
  async cancelTroop(queueId) {
    await api.cancelTroopQueue(queueId);
    await get().loadCity();
  },
  async sendMovement({ targetCityId, targetOasisId, movementType, troops, spyCount = 0, targetBuilding = null }) {
    const city = get().currentCity;
    if (!city) return null;
    const payload = {
      origin_city_id: city.id,
      movement_type: movementType,
      troops,
      spy_count: spyCount,
      target_building: targetBuilding,
      world_id: city.world_id,
    };

    if (targetOasisId) {
      payload.target_oasis_id = targetOasisId;
    } else {
      payload.target_city_id = targetCityId;
    }

    const { data } = await api.sendMovement(payload);
    await get().loadCity();
    return data;
  },
  setMovements(movements) {
    set({ movements });
  },
  async loadMovements() {
    const city = get().currentCity;
    if (!city || !city.world_id) return { movements: [] };
    const previous = get().movements || [];
    const previousAttackIds = new Set(
      previous.filter((m) => m.category === 'attack_in').map((m) => m.id)
    );
    const { data } = await api.getMovements({ worldId: city.world_id });
    const rawList = Array.isArray(data) ? data : data.movements || [];
    const ownedCityIds = new Set((get().cities || []).map((ownedCity) => ownedCity.id));
    const movementList = rawList.map((movement) => ({
      ...movement,
      direction: ownedCityIds.has(movement.origin_city_id) ? 'out' : 'in',
      category: movementCategory(movement, ownedCityIds),
    }));
    set({ movements: movementList });
    const hasNewAttackIncoming = movementList.some(
      (movement) => movement.category === 'attack_in' && !previousAttackIds.has(movement.id)
    );
    if (hasNewAttackIncoming) {
      soundManager.playSFX('attack_incoming');
    }
    return { movements: movementList };
  },
  async loadReports() {
    const city = get().currentCity;
    if (!city || !city.world_id) return { reports: [] };
    const { data } = await api.getReports({ worldId: city.world_id });
    const reportList = Array.isArray(data) ? data : data?.reports || [];
    set({ reports: reportList });
    return { reports: reportList };
  },
  async loadAlliance() {
    const city = get().currentCity;
    const { data } = await api.getAlliance(city?.world_id);
    set({ alliance: data });
    return data;
  },
  async loadMessages() {
    const previousIds = new Set(get().messages.map((m) => m.id));
    const { data } = await api.getMessages();
    set({ messages: data.messages });
    const hasNewMessage = data.messages.some((message) => !previousIds.has(message.id));
    if (hasNewMessage) {
      soundManager.playSFX('message_received');
    }
    return data;
  },
}));
