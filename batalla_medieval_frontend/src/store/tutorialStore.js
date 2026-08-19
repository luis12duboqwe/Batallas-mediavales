import { create } from 'zustand';
import { api } from '../api/axiosClient';

export const useTutorialStore = create((set) => ({
  step: 0,
  totalSteps: 7,
  isActive: false,
  completed: false,
  rewardClaimed: false,
  reward: null,
  nextAction: 'Únete a un mundo para recibir tu capital.',
  loading: false,

  fetchStatus: async () => {
    set({ loading: true });
    try {
      const { data } = await api.getTutorialStatus();
      set({
        step: data.step,
        totalSteps: data.total_steps ?? 7,
        isActive: !data.completed,
        completed: Boolean(data.completed),
        rewardClaimed: Boolean(data.reward_claimed),
        reward: data.reward ?? null,
        nextAction: data.next_action ?? '',
        loading: false,
      });
      return data;
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  advance: async () => {
    set({ loading: true });
    try {
      const { data } = await api.advanceTutorial();
      set({
        step: data.step,
        totalSteps: data.total_steps ?? 7,
        isActive: !data.completed,
        completed: Boolean(data.completed),
        rewardClaimed: Boolean(data.reward_claimed),
        reward: data.reward ?? null,
        nextAction: data.next_action ?? '',
        loading: false,
      });
      return data;
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },
}));
