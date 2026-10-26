import type { TrackedJobs } from "@/lib/processing";

const key = (songId: string) => `multitrack:jobs:${songId}`;

/** Job ids this tab last saw for a song; null when storage is unavailable or empty. */
export function readTracked(songId: string): TrackedJobs | null {
  try {
    const raw = window.sessionStorage.getItem(key(songId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<TrackedJobs>;
    return {
      analyze: typeof parsed.analyze === "string" ? parsed.analyze : null,
      separate: typeof parsed.separate === "string" ? parsed.separate : null,
    };
  } catch {
    return null;
  }
}

/** Remembers the ids and mirrors them in the address bar so a reload or a shared link keeps following. */
export function writeTracked(songId: string, tracked: TrackedJobs): void {
  try {
    window.sessionStorage.setItem(key(songId), JSON.stringify(tracked));
  } catch {
    // Storage blocked: the URL alone still carries the ids.
  }
  const params = new URLSearchParams();
  if (tracked.analyze) params.set("a", tracked.analyze);
  if (tracked.separate) params.set("s", tracked.separate);
  const query = params.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}
