/**
 * Songs this browser uploaded, kept in localStorage so a closed tab is not the end of the way
 * back to a song. Entries expire with the song (24 h); the API stays the source of truth, so the
 * list is only a bookmark. Every access is guarded: blocked, full or corrupt storage just yields
 * an empty list.
 */
import type { TrackedJobs } from "@/lib/processing";

export const RECENT_KEY = "multitrack:recent-songs";
export const MAX_STORED = 20;
export const MAX_SHOWN = 8;

const SAFE_ID = /^[A-Za-z0-9_-]{1,128}$/;

/** pending: processing or unknown; ready: analysis and stems exist; gone: the API forgot the song. */
export type RecentStatus = "pending" | "ready" | "gone";

export interface RecentSong {
  id: string;
  filename: string;
  /** Epoch milliseconds. */
  createdAt: number;
  expiresAt: number;
  jobs: TrackedJobs;
  status: RecentStatus;
}

export type RecentStore = Pick<Storage, "getItem" | "setItem">;

function defaultStore(): RecentStore | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null; // Accessing localStorage can itself throw (blocked site data).
  }
}

const jobId = (value: unknown): string | null =>
  typeof value === "string" && SAFE_ID.test(value) ? value : null;

function parseEntry(raw: unknown): RecentSong | null {
  if (typeof raw !== "object" || raw === null) return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.id !== "string" || !SAFE_ID.test(o.id)) return null;
  if (typeof o.filename !== "string" || !o.filename) return null;
  if (!Number.isFinite(o.createdAt) || !Number.isFinite(o.expiresAt)) return null;
  const jobs = typeof o.jobs === "object" && o.jobs !== null ? (o.jobs as Record<string, unknown>) : {};
  const status: RecentStatus = o.status === "ready" || o.status === "gone" ? o.status : "pending";
  return {
    id: o.id,
    filename: o.filename,
    createdAt: o.createdAt as number,
    expiresAt: o.expiresAt as number,
    jobs: { analyze: jobId(jobs.analyze), separate: jobId(jobs.separate) },
    status,
  };
}

/** Parses the stored text; anything malformed is dropped entry by entry, never thrown. */
export function parseRecent(text: string | null | undefined): RecentSong[] {
  if (!text) return [];
  try {
    const data: unknown = JSON.parse(text);
    if (!Array.isArray(data)) return [];
    return data.map(parseEntry).filter((e): e is RecentSong => e !== null);
  } catch {
    return [];
  }
}

function load(store: RecentStore | null): RecentSong[] {
  try {
    return parseRecent(store?.getItem(RECENT_KEY));
  } catch {
    return [];
  }
}

function save(entries: RecentSong[], store: RecentStore | null): void {
  try {
    store?.setItem(RECENT_KEY, JSON.stringify(entries.slice(0, MAX_STORED)));
  } catch {
    // Storage blocked or full: the list is simply not remembered.
  }
}

const alive = (entry: RecentSong, nowMs: number) => entry.expiresAt > nowMs;

/** Every remembered song that has not expired, newest first; expired ones are dropped from storage. */
export function readRecent(nowMs: number, store: RecentStore | null = defaultStore()): RecentSong[] {
  const all = load(store);
  const kept = all.filter((e) => alive(e, nowMs)).sort((a, b) => b.createdAt - a.createdAt);
  if (kept.length !== all.length) save(kept, store);
  return kept;
}

/** What the upload screen lists: unexpired, not known to be gone, at most MAX_SHOWN. */
export function visibleRecent(entries: RecentSong[], nowMs: number): RecentSong[] {
  return entries.filter((e) => e.status !== "gone" && alive(e, nowMs)).slice(0, MAX_SHOWN);
}

/** Adds a song (or refreshes the one with the same id, keeping any job ids already known). */
export function rememberSong(
  entry: Omit<RecentSong, "jobs" | "status"> & Partial<Pick<RecentSong, "jobs" | "status">>,
  nowMs: number,
  store: RecentStore | null = defaultStore(),
): RecentSong[] {
  const current = readRecent(nowMs, store);
  const previous = current.find((e) => e.id === entry.id);
  const merged: RecentSong = {
    ...entry,
    jobs: {
      analyze: entry.jobs?.analyze ?? previous?.jobs.analyze ?? null,
      separate: entry.jobs?.separate ?? previous?.jobs.separate ?? null,
    },
    status: entry.status ?? (previous?.status === "ready" ? "ready" : "pending"),
  };
  const next = [merged, ...current.filter((e) => e.id !== entry.id)].sort(
    (a, b) => b.createdAt - a.createdAt,
  );
  save(next, store);
  return next.filter((e) => alive(e, nowMs));
}

/** Merges new facts into a remembered song; unknown ids are ignored. */
export function updateRecent(
  id: string,
  patch: { jobs?: Partial<TrackedJobs>; status?: RecentStatus },
  nowMs: number,
  store: RecentStore | null = defaultStore(),
): RecentSong[] {
  const current = readRecent(nowMs, store);
  const next = current.map((e) =>
    e.id === id
      ? {
          ...e,
          jobs: {
            analyze: patch.jobs?.analyze ?? e.jobs.analyze,
            separate: patch.jobs?.separate ?? e.jobs.separate,
          },
          status: patch.status ?? e.status,
        }
      : e,
  );
  save(next, store);
  return next;
}

export const markGone = (id: string, nowMs: number, store?: RecentStore | null) =>
  updateRecent(id, { status: "gone" }, nowMs, store);

export function removeRecent(
  id: string,
  nowMs: number,
  store: RecentStore | null = defaultStore(),
): RecentSong[] {
  const next = readRecent(nowMs, store).filter((e) => e.id !== id);
  save(next, store);
  return next;
}

/** Where a remembered song leads: the studio when it is ready, else the processing view. */
export function recentHref(entry: RecentSong): string {
  if (entry.status === "ready") return `/temas/${entry.id}/estudio`;
  const params = new URLSearchParams();
  if (entry.jobs.analyze) params.set("a", entry.jobs.analyze);
  if (entry.jobs.separate) params.set("s", entry.jobs.separate);
  const query = params.toString();
  return `/temas/${entry.id}${query ? `?${query}` : ""}`;
}
