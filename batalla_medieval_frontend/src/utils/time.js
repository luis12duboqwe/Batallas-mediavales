export const formatDuration = (seconds) => {
  const s = Math.max(0, Math.floor(seconds));
  const hrs = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  return [hrs, mins, secs]
    .map((v) => v.toString().padStart(2, '0'))
    .join(':');
};

export const timeRemaining = (end) => {
  const endDate = typeof end === 'string' ? new Date(end) : end;
  const diff = (endDate.getTime() - Date.now()) / 1000;
  return Math.max(diff, 0);
};

export const addSeconds = (date, seconds) => {
  const d = typeof date === 'string' ? new Date(date) : new Date(date);
  d.setSeconds(d.getSeconds() + seconds);
  return d.toISOString();
};
