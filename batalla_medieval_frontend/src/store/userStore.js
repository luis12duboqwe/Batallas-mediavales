import { create } from 'zustand';
import { api } from '../api/axiosClient';

export const useUserStore = create((set, get) => ({
  user: null,
  token: localStorage.getItem('bm_token'),
  cities: [],
  loading: false,
  error: null,
  async login(credentials) {
    set({ loading: true, error: null });
    try {
      const { data } = await api.login(credentials);
      localStorage.setItem('bm_token', data.token);
      set({ token: data.token, user: data.user, cities: data.cities, loading: false });
      return data;
    } catch (err) {
      set({ error: err.response?.data?.detail || 'Error al iniciar sesión', loading: false });
      throw err;
    }
  },
  async register(payload) {
    set({ loading: true, error: null });
    try {
      const { data } = await api.register(payload);
      localStorage.setItem('bm_token', data.token);
      set({ token: data.token, user: data.user, cities: data.cities, loading: false });
      return data;
    } catch (err) {
      set({ error: err.response?.data?.detail || 'Error al registrarse', loading: false });
      throw err;
    }
  },
  logout() {
    localStorage.removeItem('bm_token');
    set({ user: null, token: null, cities: [] });
  },
  setCities(cities) {
    set({ cities });
  },
  async refreshCity() {
    const { data } = await api.getCities();
    set({ cities: data });
    return { cities: data };
  },
  isAuthenticated() {
    return Boolean(get().token);
  },
}));
