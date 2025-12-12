import { create } from 'zustand';
import { api } from '../api/axiosClient';

export const useThemeStore = create((set, get) => ({
  themes: [],
  currentTheme: null,
  loading: false,

  fetchThemes: async () => {
    set({ loading: true });
    try {
      const { data } = await api.getThemes();
      set({ themes: data });
      
      // Load saved theme or default
      const savedThemeId = localStorage.getItem('bm_theme_id');
      if (savedThemeId) {
        const theme = data.find(t => t.id === +savedThemeId);
        if (theme) get().setTheme(theme);
      } else if (data.length > 0) {
        // Default to first theme if none saved
        get().setTheme(data[0]);
      }
    } catch (error) {
      console.error('Failed to fetch themes', error);
    } finally {
      set({ loading: false });
    }
  },

  setTheme: (theme) => {
    set({ currentTheme: theme });
    localStorage.setItem('bm_theme_id', theme.id);
    
    // Apply styles
    const root = document.documentElement;
    root.style.setProperty('--theme-primary', theme.primary_color);
    root.style.setProperty('--theme-secondary', theme.secondary_color);
    if (theme.background_url) {
      root.style.setProperty('--theme-bg', `url('${theme.background_url}')`);
    }
  }
}));
