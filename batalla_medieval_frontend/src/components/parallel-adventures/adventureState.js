// The API stores UTC datetimes; some responses omit a timezone suffix.
const UTC_NAIVE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;

export const adventureDeadlineMs = (adventure) => {
  if (!adventure?.started_at) return null;
  const duration = Number(adventure.duration);
  if (!Number.isFinite(duration) || duration < 0) return null;

  const raw = adventure.started_at;
  if (typeof raw !== 'string') return null;
  const timestamp = UTC_NAIVE.test(raw) ? raw.replace(' ', 'T') + 'Z' : raw;
  const startMs = Date.parse(timestamp);
  const deadlineMs = startMs + duration * 1000;
  return Number.isFinite(deadlineMs) ? deadlineMs : null;
};

export const canClaimAdventure = (adventure, nowMs) => {
  const deadline = adventureDeadlineMs(adventure);
  return adventure?.status === 'active'
    && deadline !== null
    && Number.isFinite(nowMs)
    && nowMs >= deadline;
};

// Reflect only an acknowledged server mutation. This never calculates,
// grants or persists rewards in the browser.
export const applyAdventureResponse = (adventures, id, action, response) => (
  adventures.map((adventure) => {
    if (String(adventure.id) !== String(id)) return adventure;

    if (action === 'start' && response?.status === 'active') {
      return { ...adventure, ...response };
    }
    if (action === 'claim' && ['success', 'dead'].includes(response?.status)) {
      return {
        ...adventure,
        status: response.status === 'dead' ? 'failed' : 'completed',
        result: response,
      };
    }
    return adventure;
  })
);
