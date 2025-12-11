import { create } from 'zustand';
import { addSeconds } from '../utils/time';

export const useGameStore = create((set) => ({
  selectedTile: null,
  mapCenter: { x: 0, y: 0 },
  countdowns: {},
  setSelectedTile(tile) {
    set({ selectedTile: tile });
  },
  setMapCenter(center) {
    set({ mapCenter: center });
  },
  setCountdown(id, endTime) {
    set((state) => ({ countdowns: { ...state.countdowns, [id]: endTime } }));
  },
  advanceCountdowns(seconds = 1) {
    set((state) => {
      const updated = {};
      Object.entries(state.countdowns).forEach(([key, value]) => {
        updated[key] = addSeconds(value, -seconds);
      });
      return { countdowns: updated };
    });
  },
}));
