/** Pan positions remembered per song in this browser. Every storage access is guarded. */
import { clampPan } from "./mix";
import { STEM_ORDER, type StemName } from "./stems";

export type PanMap = Partial<Record<StemName, number>>;

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const key = (songId: string) => `studio:pan:${songId}`;

function defaultStore(): Store | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** Keeps only known stems with finite numbers; anything else in storage is ignored. */
export function sanitizePans(raw: unknown): PanMap {
  const out: PanMap = {};
  if (typeof raw !== "object" || raw === null) return out;
  for (const name of STEM_ORDER) {
    const value = (raw as Record<string, unknown>)[name];
    if (typeof value === "number" && Number.isFinite(value) && value !== 0) out[name] = clampPan(value);
  }
  return out;
}

export function loadPans(songId: string, store: Store | null = defaultStore()): PanMap {
  if (!store) return {};
  try {
    const text = store.getItem(key(songId));
    return text ? sanitizePans(JSON.parse(text)) : {};
  } catch {
    return {};
  }
}

/** Saves non-centre pans; an all-centre mix removes the entry. Returns false when storage refused. */
export function savePans(
  songId: string,
  pans: PanMap,
  store: Store | null = defaultStore(),
): boolean {
  if (!store) return false;
  try {
    const clean = sanitizePans(pans);
    if (Object.keys(clean).length === 0) store.removeItem(key(songId));
    else store.setItem(key(songId), JSON.stringify(clean));
    return true;
  } catch {
    return false;
  }
}
