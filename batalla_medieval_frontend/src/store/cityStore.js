import { create } from 'zustand';
import { api } from '../api/axiosClient';
import { calculateProduction } from '../utils/gameMath';
import soundManager from '../services/sound';

export const useCityStore = create((set, get) => ({
  currentCity: null,
  resources: { wood: 0, clay: 0, iron: 0, population: 0, populationMax: 0 },
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
      currentCity: data.city,
      resources: data.resources,
      buildings: data.buildings,
      productionRates: data.production,
      queues: data.queues || { buildings: [], troops: [] },
    });
    return data;
  },
  tickResources(elapsedSeconds = 1) {
    const { resources, productionRates } = get();
    const updated = calculateProduction(resources, productionRates, elapsedSeconds);
    set({ resources: updated });
  },
  async upgrade(building) {
    const { data } = await api.upgradeBuilding(building);
    set((state) => ({
      buildings: state.buildings.map((b) => (b.name === building ? data.building : b)),
      queues: { ...state.queues, buildings: data.queue },
      resources: data.resources,
    }));
    return data;
  },
  async train(payload) {
    const { data } = await api.trainTroops(payload);
    set((state) => ({
      queues: { ...state.queues, troops: data.queue },
      resources: data.resources,
    }));
    return data;
  },
  setMovements(movements) {
    set({ movements });
  },
  async loadMovements() {
    const previous = get().movements || [];
    const previousAttackIds = new Set(
      previous.filter((m) => m.category === 'attack_in').map((m) => m.id)
    );
    const { data } = await api.getMovements();
    set({ movements: data.movements });
    const hasNewAttackIncoming = data.movements.some(
      (movement) => movement.category === 'attack_in' && !previousAttackIds.has(movement.id)
    );
    if (hasNewAttackIncoming) {
      soundManager.playSFX('attack_incoming');
    }
    return data;
  },
  async loadReports() {
    const { data } = await api.getReports();
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
