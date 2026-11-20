// Missing or malformed list bodies represent an error, never an empty result.
export const readMapTilesResponse = (data) => {
  if (!data || !Array.isArray(data.tiles)) throw new Error('La respuesta del mapa es inválida.');
  return data.tiles;
};

export const readMessageListResponse = (data) => {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.messages)) return data.messages;
  throw new Error('La respuesta de mensajería es inválida.');
};

export const readReportListResponse = (data) => {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.reports)) return data.reports;
  throw new Error('La respuesta de reportes es inválida.');
};
