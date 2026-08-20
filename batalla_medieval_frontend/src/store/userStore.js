import { create } from 'zustand';
import { api } from '../api/axiosClient';

const readStoredToken = () => {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('bm_token');
};

export const useUserStore = create((set, get) => ({
  user: null,
  token: readStoredToken(),
  cities: [],
  loading: false,
  error: null,
  async login(credentials) {
    set({ loading: true, error: null });
    try {
      const { data } = await api.login(credentials);
      const accessToken = data.access_token;
      window.localStorage.setItem('bm_token', accessToken);
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
    window.localStorage.removeItem('bm_token');
    set({ user: null, token: null, cities: [], error: null });
  },
  hydrateSession() {
    const storedToken = readStoredToken();
    if (storedToken && get().token !== storedToken) {
      set({ token: storedToken });
    }
    return storedToken;
  },
  setCities(cities) {
    set({ cities });
  },
  async refreshCity() {
    const token = get().token || get().hydrateSession();
    if (!token) return null;
    try {
      const { data } = await api.getCity();
      set({ user: data.user, cities: data.cities });
      return data;
    } catch (err) {
      if (err.response?.status === 401) {
        get().logout();
      }
      throw err;
    }
  },
  async loadUser() {
    const token = get().token || get().hydrateSession();
    if (!token) return null;
    try {
      const { data } = await api.getProfile();
      set({ user: data });
      return data;
    } catch (err) {
      if (err.response?.status === 401) {
        get().logout();
      }
      throw err;
    }
  },
  isAuthenticated() {
    return Boolean(get().token || readStoredToken());
  },
}));
