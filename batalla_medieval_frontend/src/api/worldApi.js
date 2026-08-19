import axiosClient from './axiosClient';

export const worldApi = {
  listWorlds: () => axiosClient.get('/worlds/'),

  // user.world_id is the persisted selector already used by city loading.
  // Reading it from the authenticated profile keeps reload/re-login aligned
  // with the durable session state and avoids an extra boot-time endpoint.
  getActiveWorld: async () => {
    const profile = await axiosClient.get('/auth/me');
    return { data: { id: profile.data.world_id ?? null } };
  },

  setActiveWorld: (worldId) =>
    axiosClient.post('/worlds/active', { world_id: worldId }),

  joinWorld: (worldId) =>
    axiosClient.post(`/worlds/${worldId}/join`),
};

export default worldApi;
