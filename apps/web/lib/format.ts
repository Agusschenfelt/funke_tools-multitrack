/** File size in the es-AR convention: decimal comma, binary units. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const text = value.toLocaleString("es-AR", { maximumFractionDigits: value >= 100 ? 0 : 1 });
  return `${text} ${units[unit]}`;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

/** "hace 5 min", "hace 2 h", "hace 3 d": how long ago, in the es-AR voice of the app. */
export function formatAgo(elapsedMs: number): string {
  const ms = Math.max(0, elapsedMs);
  if (ms < MINUTE) return "hace un momento";
  if (ms < HOUR) return `hace ${Math.floor(ms / MINUTE)} min`;
  if (ms < 24 * HOUR) return `hace ${Math.floor(ms / HOUR)} h`;
  return `hace ${Math.floor(ms / (24 * HOUR))} d`;
}

/** "21 h 40 min", "35 min", "menos de 1 min": time before something expires. */
export function formatTimeLeft(remainingMs: number): string {
  if (remainingMs < MINUTE) return "menos de 1 min";
  const hours = Math.floor(remainingMs / HOUR);
  const minutes = Math.floor((remainingMs % HOUR) / MINUTE);
  if (hours === 0) return `${minutes} min`;
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`;
}
