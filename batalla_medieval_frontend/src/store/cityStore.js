import { create } from 'zustand';
import { api } from '../api/axiosClient';
import { calculateProduction } from '../utils/gameMath';

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
  async loadCity(cityId) {
    let targetCityId = cityId;

    if (!targetCityId) {
      const { data: cities } = await api.getCities();
      if (!cities?.length) {
        throw new Error('No hay ciudades disponibles');
      }
      targetCityId = cities[0].id;
    }

    const { data } = await api.getCity(targetCityId);
    set({
      currentCity: data,
      resources: {
        wood: data.wood,
        clay: data.clay,
        iron: data.iron,
        population: data.population || 0,
        populationMax: data.populationMax || 0,
      },
      buildings: data.buildings || [],
      productionRates: data.production || { wood: 0, clay: 0, iron: 0 },
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
    const { currentCity } = get();
    const { data } = await api.upgradeBuilding(currentCity?.id, building);
    set((state) => ({
      buildings: state.buildings.map((b) => (b.name === building ? data.building : b)),
      queues: { ...state.queues, buildings: data.queue },
      resources: data.resources,
    }));
    return data;
  },
  async train(payload) {
    const { currentCity } = get();
    const { data } = await api.trainTroops(currentCity?.id, payload);
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
    const { data } = await api.getMovements();
    set({ movements: data.movements });
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
    const { data } = await api.getMessages();
    set({ messages: data.messages });
    return data;
  },
}));
