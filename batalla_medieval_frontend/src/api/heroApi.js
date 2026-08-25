import axiosClient from './axiosClient';

const params = (worldId) => ({ params: { world_id: worldId } });

export const heroApi = {
  getRules: () => axiosClient.get('/economy/balance_preview'),
  getHero: (worldId) => axiosClient.get('/hero/', params(worldId)),
  distributePoints: (worldId, points) => axiosClient.post('/hero/distribute', points, params(worldId)),
  revive: (worldId) => axiosClient.post('/hero/revive', {}, params(worldId)),
  getItems: (worldId) => axiosClient.get('/hero/items', params(worldId)),
  equipItem: (worldId, itemId) => axiosClient.post(`/hero/items/${itemId}/equip`, {}, params(worldId)),
  unequipItem: (worldId, itemId) => axiosClient.post(`/hero/items/${itemId}/unequip`, {}, params(worldId)),
  getAdventures: (worldId) => axiosClient.get('/adventure/', params(worldId)),
  startAdventure: (worldId, adventureId) => axiosClient.post(`/adventure/${adventureId}/start`, {}, params(worldId)),
  claimAdventure: (worldId, adventureId) => axiosClient.post(`/adventure/${adventureId}/claim`, {}, params(worldId)),
};

export default heroApi;
