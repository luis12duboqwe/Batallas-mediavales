export const formatNumber = (value) => {
  if (value === undefined || value === null) return '0';
  return Number(value).toLocaleString('es-ES');
};

export const formatResource = (value, suffix = '') => `${formatNumber(value)}${suffix}`;

export const formatDate = (date) => new Date(date).toLocaleString('es-ES');
