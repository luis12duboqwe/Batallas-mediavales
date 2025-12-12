import { create } from 'zustand';
import { api } from '../api/axiosClient';
import { calculateProduction } from '../utils/gameMath';
import soundManager from '../services/sound';

export const useCityStore = create((set, get) => ({
  currentCity: null,
  resources: { wood: 0, clay: 0, iron: 0, population: 0, populationMax: 0 },
  storageLimit: 5000,
  buildings: [],
  productionRates: { wood: 0, clay: 0, iron: 0 },
  queues: { buildings: [], troops: [] },
  movements: [],
  reports: [],
  alliance: null,
  messages: [],
  async loadCity() {
    const { data } = await api.getCity();
    set({
      currentCity: { id: data.city_id, ...data.city }, // Ensure ID is available
      resources: data.resources,
      storageLimit: data.storage_limit || 5000,
      buildings: data.buildings,
      productionRates: data.production,
      queues: data.queues || { buildings: [], troops: [] },
    });
    return data;
  },
  tickResources(elapsedSeconds = 1) {
    const { resources, productionRates, storageLimit } = get();
    // Simple client-side prediction
    const updated = { ...resources };
    ['wood', 'clay', 'iron'].forEach(res => {
        const produced = (productionRates[res] / 3600) * elapsedSeconds;
        updated[res] = Math.min(updated[res] + produced, storageLimit);
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
    set((state) => ({
      // backend returns queue entry; we keep optimistic queue listing
      queues: {
        ...state.queues,
        buildings: [...(state.queues.buildings || []), data],
      },
    }));
    return data;
  },
  async cancelBuilding(queueId) {
    await api.cancelBuildingQueue(queueId);
    set((state) => ({
      queues: {
        ...state.queues,
        buildings: state.queues.buildings.filter((q) => q.id !== queueId),
      },
    }));
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
    set((state) => ({
      queues: {
        ...state.queues,
        troops: [...(state.queues.troops || []), data],
      },
    }));
    return data;
  },
  async cancelTroop(queueId) {
    await api.cancelTroopQueue(queueId);
    set((state) => ({
      queues: {
        ...state.queues,
        troops: state.queues.troops.filter((q) => q.id !== queueId),
      },
    }));
  },
  async sendMovement({ targetCityId, targetOasisId, movementType, troops, targetBuilding = null }) {
    const city = get().currentCity;
    if (!city) return null;
    const payload = {
      origin_city_id: city.id,
      movement_type: movementType,
      troops: troops,
      target_building: targetBuilding,
      world_id: city.world_id,
    };

    if (targetOasisId) {
        payload.target_oasis_id = targetOasisId;
    } else {
        payload.target_city_id = targetCityId;
    }

    const { data } = await api.sendMovement(payload);
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
    const movementList = rawList.map((movement) => ({
      category: movement.category || (movement.movement_type === 'attack' ? 'attack_out' : movement.movement_type),
      ...movement,
    }));
    set({ movements: movementList });
    const hasNewAttackIncoming = movementList.some(
      (movement) => movement.category === 'attack_in' && !previousAttackIds.has(movement.id)
    );
    if (hasNewAttackIncoming) {
      soundManager.playSFX('attack_incoming');
    }
    return data;
  },
  async loadReports() {
    const city = get().currentCity;
    if (!city || !city.world_id) return { reports: [] };
    const { data } = await api.getReports({ worldId: city.world_id });
    set({ reports: data.reports });
    return data;
  },
  async loadAlliance() {
    const { data } = await api.getAlliance();
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
