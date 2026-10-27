/**
 * Stage Pack options: defaults, the request body and what we remember per browser.
 * The choices mirror `StagePackOptions` in `packages/audio-core/audio_core/models.py`.
 */
import type { StagePackOptions } from "@/lib/api";
import type { ClickSound } from "@/lib/audio/click";

export type { ClickSound };

export type Destination = "playback" | "daw";

export interface ExportOptions {
  destination: Destination;
  countInBars: 1 | 2;
  clickSound: ClickSound;
  subdivision: "quarter" | "eighth";
  straightGrid: boolean;
  sampleRate: 44100 | 48000;
  includeVocals: boolean;
  extendGrid: boolean;
  language: "es" | "en";
}

/** The same defaults the server applies to an omitted field (destination has none: Playback here). */
export const DEFAULT_OPTIONS: ExportOptions = {
  destination: "playback",
  countInBars: 1,
  clickSound: "classic",
  subdivision: "quarter",
  straightGrid: false,
  sampleRate: 44100,
  includeVocals: false,
  extendGrid: true,
  language: "es",
};

/** The full request body: every field explicit, so the server never guesses. */
export function toApiBody(o: ExportOptions): Required<StagePackOptions> {
  return {
    destination: o.destination,
    count_in_bars: o.countInBars,
    click_sound: o.clickSound,
    subdivision: o.subdivision,
    straight_grid: o.straightGrid,
    sample_rate: o.sampleRate,
    include_vocals: o.includeVocals,
    extend_grid: o.extendGrid,
    language: o.language,
  };
}

const pick = <T,>(value: unknown, allowed: readonly T[], fallback: T): T =>
  (allowed as readonly unknown[]).includes(value) ? (value as T) : fallback;

/** Anything stored that is not a valid choice falls back to its default, field by field. */
export function parseOptions(raw: unknown): ExportOptions {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const d = DEFAULT_OPTIONS;
  return {
    destination: pick(o.destination, ["playback", "daw"], d.destination),
    countInBars: pick(o.countInBars, [1, 2], d.countInBars),
    clickSound: pick(o.clickSound, ["classic", "cowbell", "woodblock", "rimshot"], d.clickSound),
    subdivision: pick(o.subdivision, ["quarter", "eighth"], d.subdivision),
    straightGrid: typeof o.straightGrid === "boolean" ? o.straightGrid : d.straightGrid,
    sampleRate: pick(o.sampleRate, [44100, 48000], d.sampleRate),
    includeVocals: typeof o.includeVocals === "boolean" ? o.includeVocals : d.includeVocals,
    extendGrid: typeof o.extendGrid === "boolean" ? o.extendGrid : d.extendGrid,
    language: pick(o.language, ["es", "en"], d.language),
  };
}

const STORAGE_KEY = "multitrack:export-options";

type Store = Pick<Storage, "getItem" | "setItem">;

function defaultStore(): Store | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null; // Accessing localStorage can itself throw (blocked site data).
  }
}

/** Last options used in this browser; defaults when storage is blocked, empty or corrupt. */
export function readOptions(store: Store | null = defaultStore()): ExportOptions {
  try {
    const raw = store?.getItem(STORAGE_KEY);
    return raw ? parseOptions(JSON.parse(raw)) : DEFAULT_OPTIONS;
  } catch {
    return DEFAULT_OPTIONS;
  }
}

export function writeOptions(options: ExportOptions, store: Store | null = defaultStore()): void {
  try {
    store?.setItem(STORAGE_KEY, JSON.stringify(options));
  } catch {
    // Storage blocked or full: the choices simply are not remembered.
  }
}
