import axiosClient from './axiosClient';

export const expansionApi = {
  getStatus: (worldId) => axiosClient.get('/expansion/status', {
    params: { world_id: worldId },
  }),
  found: (payload) => axiosClient.post('/expansion/found', payload),
  promoteCamp: (campId) => axiosClient.post(`/expansion/camps/${campId}/promote`),
};

export default expansionApi;
