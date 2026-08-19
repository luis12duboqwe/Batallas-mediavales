import { create } from 'zustand';
import { api } from '../api/axiosClient';

const snapshotToState = (data) => ({
  step: data.step,
  totalSteps: data.total_steps ?? 7,
  isActive: !data.completed,
  completed: Boolean(data.completed),
  rewardClaimed: Boolean(data.reward_claimed),
  reward: data.reward ?? null,
  nextAction: data.next_action ?? '',
});

export const useTutorialStore = create((set, get) => ({
  step: 0,
  totalSteps: 7,
  isActive: false,
  completed: false,
  rewardClaimed: false,
  reward: null,
  nextAction: 'Únete a un mundo para recibir tu capital.',
  loading: false,

  fetchStatus: async () => {
    if (get().loading) return null;
    set({ loading: true });
    try {
      const statusResponse = await api.getTutorialStatus();
      let snapshot = statusResponse.data;

      // GET /tutorial/status is deliberately read-only. Claim the final reward
      // once only after the server has independently derived completion.
      if (snapshot.completed && !snapshot.reward_claimed) {
        const claimResponse = await api.advanceTutorial();
        snapshot = claimResponse.data;
      }

      set({ ...snapshotToState(snapshot), loading: false });
      return snapshot;
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  advance: async () => {
    set({ loading: true });
    try {
      const { data } = await api.advanceTutorial();
      set({ ...snapshotToState(data), loading: false });
      return data;
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },
}));
