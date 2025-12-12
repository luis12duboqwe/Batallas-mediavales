import { create } from 'zustand';
import worldApi from '../api/worldApi';

export const useWorldStore = create((set, get) => ({
  worlds: [],
  currentWorldId: null,
  loading: false,
  error: null,

  async loadWorlds() {
    set({ loading: true, error: null });
    try {
      const { data } = await worldApi.getActiveWorld();
      set({
        worlds: data.worlds || [],
        currentWorldId: data.current_world_id,
        loading: false,
      });
      return data;
    } catch (err) {
      set({ error: err.response?.data?.detail || 'Error al cargar mundos', loading: false });
      throw err;
    }
  },

  async setActiveWorld(worldId) {
    set({ loading: true, error: null });
    try {
      await worldApi.setActiveWorld(worldId);
      set({ currentWorldId: worldId, loading: false });
      return worldId;
    } catch (err) {
      set({ error: err.response?.data?.detail || 'Error al seleccionar mundo', loading: false });
      throw err;
    }
  },

  async joinWorld(worldId) {
    set({ loading: true, error: null });
    try {
      const { data } = await worldApi.joinWorld(worldId);
      set({ currentWorldId: worldId, loading: false });
      return data;
    } catch (err) {
      set({ error: err.response?.data?.detail || 'Error al unirse al mundo', loading: false });
      throw err;
    }
  },
}));
