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
  login: (data) => axiosClient.post('/login', data),
  register: (data) => axiosClient.post('/register', data),
  getCity: () => axiosClient.get('/city'),
  updateCity: (data) => axiosClient.put('/city', data),
  upgradeBuilding: (building) => axiosClient.post('/city/upgrade', { building }),
  trainTroops: (payload) => axiosClient.post('/troops/train', payload),
  sendMovement: (payload) => axiosClient.post('/movements', payload),
  getMovements: () => axiosClient.get('/movements'),
  getReports: () => axiosClient.get('/reports'),
  getAlliance: () => axiosClient.get('/alliance'),
  getMessages: () => axiosClient.get('/messages'),
};

export default axiosClient;
