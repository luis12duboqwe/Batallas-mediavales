import axiosClient from './axiosClient';

export const researchApi = {
  getQueue: (worldId) =>
    axiosClient.get('/queue/research', { params: { world_id: worldId } }),
  queue: (cityId, worldId, unitType) =>
    axiosClient.post(
      '/troop/research',
      { city_id: cityId, unit_type: unitType },
      { params: { world_id: worldId } },
    ),
  cancel: (queueId) => axiosClient.delete(`/queue/research/${queueId}`),
};

export default researchApi;
