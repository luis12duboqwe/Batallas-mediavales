import { create } from 'zustand';
import { api } from '../api/axiosClient';

export const useUserStore = create((set, get) => ({
  user: null,
  token: localStorage.getItem('bm_token'),
  cities: [],
  loading: false,
  error: null,
  isAuthenticated: () => !!get().token,
  async login(credentials) {
    set({ loading: true, error: null });
    try {
      const { data } = await api.login(credentials);
      const accessToken = data.access_token;
      localStorage.setItem('bm_token', accessToken);
      const profileResp = await api.getProfile();
      set({ token: accessToken, user: profileResp.data, loading: false });
      return { token: accessToken, user: profileResp.data };
    } catch (err) {
      set({ error: err.response?.data?.detail || 'Error al iniciar sesión', loading: false });
      throw err;
    }
  },
  async register(payload) {
    set({ loading: true, error: null });
    try {
      await api.register(payload);
      set({ loading: false });
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
    const { data } = await api.getCity();
    set({ user: data.user, cities: data.cities });
    return data;
  },
  async loadUser() {
    try {
      const { data } = await api.getProfile();
      set({ user: data });
      return data;
    } catch (err) {
      console.error(err);
    }
  },
  isAuthenticated() {
    return Boolean(get().token);
  },
}));
