import axiosClient from './axiosClient';

export const worldApi = {
  listWorlds: () => axiosClient.get('/worlds/'),

  // Build the selector snapshot from the same durable sources used elsewhere:
  // the world catalogue plus the authenticated profile's persisted world_id.
  getActiveWorld: async () => {
    const [worldsResponse, profileResponse] = await Promise.all([
      axiosClient.get('/worlds/'),
      axiosClient.get('/auth/me'),
    ]);
    return {
      data: {
        worlds: worldsResponse.data || [],
        current_world_id: profileResponse.data.world_id ?? null,
      },
    };
  },

  setActiveWorld: (worldId) =>
    axiosClient.post('/worlds/active', { world_id: worldId }),

  joinWorld: (worldId) =>
    axiosClient.post(`/worlds/${worldId}/join`),
};

export default worldApi;
