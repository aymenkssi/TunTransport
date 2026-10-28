// Display helpers for durations, distances and timetable times.

export function formatEta(seconds: number): string {
  if (seconds < 60) return "< 1 min";
  return `${Math.round(seconds / 60)} min`;
}

export function formatAge(seconds: number): string {
  if (seconds < 60) return `il y a ${Math.max(0, Math.round(seconds))} s`;
  return `il y a ${Math.round(seconds / 60)} min`;
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1).replace(".", ",")} km`;
}

/** Prochains horaires « HH:MM » à partir de maintenant (horaires théoriques). */
export function nextTimes(times: string[] | undefined, now: Date, count = 2): string[] {
  if (!times) return [];
  const minutes = now.getHours() * 60 + now.getMinutes();
  return times
    .filter((t) => {
      const [h, m] = t.split(":").map(Number);
      return h * 60 + m >= minutes;
    })
    .slice(0, count);
}
