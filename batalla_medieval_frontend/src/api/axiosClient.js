import axios from 'axios';

const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  withCredentials: true,
});

axiosClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('bm_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const api = {
  login: (data) =>
    axiosClient.post(
      '/auth/token',
      new URLSearchParams({ username: data.username, password: data.password }),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    ),
  register: (data) => axiosClient.post('/auth/register', data),
  getCities: () => axiosClient.get('/cities'),
  getCity: (cityId) => axiosClient.get(`/cities/${cityId}`),
  updateCity: (cityId, data) => axiosClient.put(`/cities/${cityId}`, data),
  upgradeBuilding: (cityId, building) => axiosClient.post(`/buildings/${cityId}`, { name: building }),
  trainTroops: (cityId, payload) => axiosClient.post(`/troops/${cityId}`, payload),
  sendMovement: (payload) => axiosClient.post('/movements', payload),
  getMovements: () => axiosClient.get('/movements'),
  getReports: () => axiosClient.get('/reports'),
  getAlliance: () => axiosClient.get('/alliance'),
  getMessages: () => axiosClient.get('/messages'),
};

export default axiosClient;
