import { create } from 'zustand';
import { api } from '../api/axiosClient';

export const useTutorialStore = create((set, get) => ({
  step: 0,
  isActive: false,
  
  fetchStatus: async () => {
    try {
      const { data } = await api.getTutorialStatus();
      set({ step: data.step, isActive: data.step < 7 });
    } catch (error) {
      console.error('Failed to fetch tutorial status', error);
    }
  },

  advance: async (targetStep) => {
    const currentStep = get().step;
    if (targetStep <= currentStep) return;

    try {
      await api.advanceTutorial(targetStep);
      set({ step: targetStep, isActive: targetStep < 7 });
    } catch (error) {
      console.error('Failed to advance tutorial', error);
    }
  },
  
  reset: () => set({ step: 0, isActive: true }),
}));
