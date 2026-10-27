/** How a song is named in the studio: readable fallbacks for generic file names, and a local rename. */
import { formatClock } from "@/lib/audio/grid";
import { titleFromFilename } from "@/lib/strip";

export const UNTITLED = "Tema sin título";
export const MAX_TITLE = 80;

/** Words a recorder, phone or DAW puts in a file name when nobody named the song. */
const GENERIC_WORDS = [
  "untitled",
  "unnamed",
  "audio",
  "track",
  "pista",
  "song",
  "cancion",
  "canción",
  "recording",
  "record",
  "grabacion",
  "grabación",
  "voice memo",
  "nota de voz",
  "new recording",
  "nueva grabacion",
  "nueva grabación",
  "whatsapp audio",
  "sin titulo",
  "sin título",
  "master",
  "mix",
  "mezcla",
  "bounce",
  "demo",
  "archivo",
];

const GENERIC = new RegExp(
  `^(?:${GENERIC_WORDS.map((w) => w.replace(/ /g, "[\\s_-]*")).join("|")})?[\\s_.\\-()\\d]*$`,
  "i",
);

/** A name that says nothing about the song: empty, only digits, or a stock word plus a number. */
export function isGenericTitle(raw: string): boolean {
  const base = titleFromFilename(raw).trim();
  return base === "" || GENERIC.test(base);
}

/** A rename as stored: trimmed, single-spaced, capped; null when nothing is left. */
export function sanitizeTitle(input: string): string | null {
  const clean = input.replace(/[\u0000-\u001f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, MAX_TITLE).trim();
  return clean === "" ? null : clean;
}

export interface TitleView {
  /** What the song bar shows. */
  text: string;
  /** The duration, shown next to a generic title so two untitled songs can be told apart. */
  detail: string | null;
  /** The shown name is the fallback, not something the user or the file said. */
  fallback: boolean;
  /** The user renamed the song in this browser. */
  renamed: boolean;
}

export function titleView(filename: string, duration: number, custom: string | null): TitleView {
  const renamed = custom !== null && custom !== "";
  if (renamed) return { text: custom, detail: null, fallback: false, renamed: true };
  if (isGenericTitle(filename)) {
    return {
      text: UNTITLED,
      detail: duration > 0 ? formatClock(duration) : null,
      fallback: true,
      renamed: false,
    };
  }
  return { text: titleFromFilename(filename), detail: null, fallback: false, renamed: false };
}

/* ------------------------------------------------------------- local storage */

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const key = (songId: string) => `studio:title:${songId}`;

function defaultStore(): Store | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function loadTitle(songId: string, store: Store | null = defaultStore()): string | null {
  if (!store) return null;
  try {
    const text = store.getItem(key(songId));
    return text === null ? null : sanitizeTitle(text);
  } catch {
    return null;
  }
}

/** Saves the rename, or forgets it when empty. Returns false when storage refused. */
export function saveTitle(songId: string, title: string | null, store: Store | null = defaultStore()): boolean {
  if (!store) return false;
  try {
    const clean = title === null ? null : sanitizeTitle(title);
    if (clean === null) store.removeItem(key(songId));
    else store.setItem(key(songId), clean);
    return true;
  } catch {
    return false;
  }
}
