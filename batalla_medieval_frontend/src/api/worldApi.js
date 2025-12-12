import axiosClient from './axiosClient';

export const worldApi = {
  listWorlds: () => axiosClient.get('/worlds/'),
  
  getActiveWorld: () => axiosClient.get('/worlds/active'),
  
  setActiveWorld: (worldId) => 
    axiosClient.post('/worlds/active', { world_id: worldId }),
  
  joinWorld: (worldId) => 
    axiosClient.post(`/worlds/${worldId}/join`),
};

export default worldApi;
