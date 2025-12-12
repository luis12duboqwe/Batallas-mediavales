import axios from 'axios';

const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/',
  withCredentials: true,
});

axiosClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('bm_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const PRODUCTION_PER_HOUR = {
  wood: 15 * 60,
  clay: 12 * 60,
  iron: 10 * 60,
};

const EMPTY_OVERVIEW = {
  wood: 0,
  clay: 0,
  iron: 0,
  population: 0,
  populationMax: 0,
  loyalty: 0,
};

const buildResourceSnapshot = (city) => {
  if (!city) {
    return { ...EMPTY_OVERVIEW };
  }
  const population = Array.isArray(city.troops)
    ? city.troops.reduce((total, troop) => total + (troop.quantity || 0), 0)
    : 0;
  return {
    wood: city.wood ?? 0,
    clay: city.clay ?? 0,
    iron: city.iron ?? 0,
    population,
    populationMax: city.population_max ?? 0,
    loyalty: city.loyalty ?? 0,
  };
};

export const api = {
  login: (data) => {
    const form = new URLSearchParams();
    form.append('username', data.username);
    form.append('password', data.password);
    return axiosClient.post('/auth/token', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
  register: (data) => axiosClient.post('/auth/register', data),
  verifyEmail: (token) => axiosClient.post(`/auth/verify-email?token=${token}`),
  forgotPassword: (email) => axiosClient.post('/auth/forgot-password', { email }),
  resetPassword: (token, newPassword) => axiosClient.post('/auth/reset-password', { token, new_password: newPassword }),
  getProfile: () => axiosClient.get('/auth/me'),
  updateProfile: (data) => axiosClient.patch('/auth/me', data),
  getCity: async ({ worldId, cityId } = {}) => {
    const profileResp = await axiosClient.get('/auth/me');
    const resolvedWorldId = worldId ?? profileResp.data.world_id ?? null;

    let cities = [];
    if (resolvedWorldId) {
      const citiesResp = await axiosClient.get('/city/', { params: { world_id: resolvedWorldId } });
      cities = citiesResp.data || [];
    }

    const activeCity = cityId
      ? cities.find((city) => city.id === cityId) || cities[0] || null
      : cities[0] || null;

    let statusData = null;
    let availableBuildings = [];

    if (activeCity && resolvedWorldId) {
      try {
        const [statusResp, availableResp] = await Promise.all([
          axiosClient.get(`/city/${activeCity.id}/status`, { params: { world_id: resolvedWorldId } }),
          axiosClient.get('/building/available', { params: { city_id: activeCity.id, world_id: resolvedWorldId } })
        ]);
        statusData = statusResp.data;
        availableBuildings = availableResp.data;
      } catch (error) {
        console.warn('Unable to load city status or buildings', error);
      }
    }

    let queueData = { building_queues: [], troop_queues: [] };
    if (statusData) {
      queueData = {
        building_queues: statusData.building_queue || [],
        troop_queues: statusData.troop_queue || [],
      };
    } else if (resolvedWorldId) {
      try {
        const queueResp = await axiosClient.get('/queue/status', { params: { world_id: resolvedWorldId } });
        queueData = queueResp.data || queueData;
      } catch (error) {
        console.warn('Unable to load queue status', error);
      }
    }

    return {
      data: {
        user: profileResp.data,
        cities,
        city: activeCity,
        resources: statusData ? statusData : buildResourceSnapshot(activeCity),
        buildings: availableBuildings.length > 0 ? availableBuildings : (activeCity?.buildings ?? []),
        production: statusData?.production_per_hour ?? { ...PRODUCTION_PER_HOUR },
        queues: {
          buildings: queueData?.building_queues ?? [],
          troops: queueData?.troop_queues ?? [],
        },
      },
    };
  },
  updateCity: (data) => axiosClient.put('/city', data),
  upgradeBuilding: ({ cityId, buildingType, worldId }) =>
    axiosClient.post(
      '/building/upgrade',
      { city_id: cityId, building_type: buildingType },
      { params: { world_id: worldId } },
    ),
  cancelBuildingQueue: (queueId) => axiosClient.delete(`/building/queue/${queueId}`),
  trainTroops: ({ cityId, troopType, amount, worldId }) =>
    axiosClient.post(
      '/troop/train',
      { city_id: cityId, troop_type: troopType, amount },
      { params: { world_id: worldId } },
    ),
  cancelTroopQueue: (queueId) => axiosClient.delete(`/troop/queue/${queueId}`),
  sendMovement: (payload) => {
    const { worldId, world_id, ...rest } = payload || {};
    const finalPayload = { ...rest, world_id: worldId ?? world_id };
    return axiosClient.post('/movement/', finalPayload);
  },
  getMovements: ({ worldId }) => axiosClient.get('/movement/', { params: { world_id: worldId } }),
  getReports: ({ worldId }) => axiosClient.get('/report/', { params: { world_id: worldId } }),
  getAlliance: () => axiosClient.get('/alliance'),
  getMessages: () => axiosClient.get('/message/inbox'),
  getInbox: () => axiosClient.get('/message/inbox'),
  getSent: () => axiosClient.get('/message/sent'),
  sendMessage: (data) => axiosClient.post('/message/send', data),
  readMessage: (id) => axiosClient.get(`/message/${id}`),
  deleteMessage: (id) => axiosClient.delete(`/message/${id}`),
  searchPlayers: (worldId, query) => axiosClient.get('/ranking/search', { params: { world_id: worldId, query } }),
  getInvitations: (worldId) => axiosClient.get('/alliance/invitations', { params: { world_id: worldId } }),
  acceptInvitation: (invitationId) => axiosClient.post(`/alliance/invitations/${invitationId}/accept`),
  invitePlayer: (allianceId, userId) => axiosClient.post(`/alliance/${allianceId}/invite`, { user_id: userId }),
  getWorlds: () => axiosClient.get('/worlds/'),
  getActiveWorld: () => axiosClient.get('/worlds/active'),
  setActiveWorld: (worldId) => axiosClient.post('/worlds/active', { world_id: worldId }),
  joinWorld: (worldId) => axiosClient.post(`/worlds/${worldId}/join`),
  getCityStatus: ({ cityId, worldId }) =>
    axiosClient.get(`/city/${cityId}/status`, { params: { world_id: worldId } }),
  
  // Map
  getMapTiles: (worldId, x, y, radius = 10) => axiosClient.get('/map/tiles', { params: { world_id: worldId, x, y, radius } }),
  getOasis: (oasisId) => axiosClient.get(`/map/oasis/${oasisId}`),
  
  // Themes
  getThemes: () => axiosClient.get('/theme/'),

  // Admin
  adminUpdateResources: (cityId, resources) => axiosClient.patch(`/admin/city/${cityId}/resources`, resources),
  adminSetBuildingLevel: (cityId, buildingType, level) => axiosClient.patch(`/admin/city/${cityId}/building/${buildingType}`, { new_level: level }),
  adminSetTroops: (cityId, troops) => axiosClient.patch(`/admin/city/${cityId}/troops`, { troops }),
  adminCreateCity: (data) => axiosClient.post('/admin/city/create', data),
  adminTeleportCity: (cityId, x, y) => axiosClient.patch(`/admin/city/${cityId}/coordinates`, { x, y }),
  adminDeleteUser: (userId) => axiosClient.delete(`/admin/user/${userId}`),
  adminDeleteCity: (cityId) => axiosClient.delete(`/admin/city/${cityId}`),

  // Troops
  researchUnit: (cityId, worldId, unitType) => axiosClient.post('/troop/research', { city_id: cityId, unit_type: unitType }, { params: { world_id: worldId } }),

  // Hero
  getHeroItems: () => axiosClient.get('/hero/items'),
  equipHeroItem: (itemId) => axiosClient.post(`/hero/items/${itemId}/equip`),
  unequipHeroItem: (itemId) => axiosClient.post(`/hero/items/${itemId}/unequip`),
  getAdventures: () => axiosClient.get('/adventure/'),
  startAdventure: (adventureId) => axiosClient.post(`/adventure/${adventureId}/start`),
  claimAdventure: (adventureId) => axiosClient.post(`/adventure/${adventureId}/claim`),

  // Market
  getOffers: (worldId, filterAlliance = false) => axiosClient.get('/market/offers', { params: { world_id: worldId, filter_alliance: filterAlliance } }),
  createOffer: (cityId, worldId, data) => axiosClient.post('/market/offers', data, { params: { city_id: cityId, world_id: worldId } }),
  acceptOffer: (offerId, cityId, worldId) => axiosClient.post(`/market/offers/${offerId}/accept`, {}, { params: { city_id: cityId, world_id: worldId } }),
  cancelOffer: (offerId, cityId, worldId) => axiosClient.delete(`/market/offers/${offerId}`, { params: { city_id: cityId, world_id: worldId } }),
  sendResources: (cityId, worldId, data) => axiosClient.post('/market/transport', data, { params: { city_id: cityId, world_id: worldId } }),
  npcTrade: (cityId, worldId, offerType, requestType, amount) => axiosClient.post('/market/npc_trade', null, { params: { city_id: cityId, world_id: worldId, offer_type: offerType, request_type: requestType, amount } }),

  // Alliance
  sendMassMessage: (allianceId, subject, content) => axiosClient.post(`/alliance/${allianceId}/mass-message`, { subject, content }),

  // Diplomacy
  getDiplomacy: (allianceId) => axiosClient.get(`/alliance/${allianceId}/diplomacy`),
  requestDiplomacy: (allianceId, targetId, status) => axiosClient.post(`/alliance/${allianceId}/diplomacy`, { alliance_target_id: targetId, status }),
  acceptDiplomacy: (allianceId, diplomacyId) => axiosClient.post(`/alliance/${allianceId}/diplomacy/${diplomacyId}/accept`),
  cancelDiplomacy: (allianceId, diplomacyId) => axiosClient.delete(`/alliance/${allianceId}/diplomacy/${diplomacyId}`),

  // Forum
  getForumThreads: (allianceId) => axiosClient.get(`/forum/alliance/${allianceId}/threads`),
  createForumThread: (allianceId, title, content) => axiosClient.post(`/forum/alliance/${allianceId}/threads`, { title, content }),
  getForumThread: (threadId) => axiosClient.get(`/forum/threads/${threadId}`),
  replyForumThread: (threadId, content) => axiosClient.post(`/forum/threads/${threadId}/reply`, { content }),

  // Tutorial
  getTutorialStatus: () => axiosClient.get('/tutorial/status'),
  advanceTutorial: (step) => axiosClient.post('/tutorial/advance', { step }),
};

export default axiosClient;
