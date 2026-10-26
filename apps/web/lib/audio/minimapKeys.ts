import { upperBound } from "./grid";

/** Bars moved by PageUp / PageDown. */
export const PAGE_BARS = 4;
/** Seconds moved by the arrows and Page keys (x4) when the song has no bar grid. */
export const FALLBACK_STEP = 5;
/** Further than this into a bar, ArrowLeft returns to that bar's start before going to the previous. */
const BAR_RESTART_AFTER = 1;
const EPS = 1e-3;

export interface KeyContext {
  /** Playhead position in seconds. */
  now: number;
  downbeats: readonly number[];
  duration: number;
}

/**
 * Seek target in seconds for a key pressed on the minimap, or null when the key is not handled.
 * Left/Right: one bar. PageUp/PageDown: four bars. Home/End: start and end. Without downbeats
 * the arrows move 5 s and the Page keys 20 s.
 */
export function minimapSeekTarget(key: string, { now, downbeats, duration }: KeyContext): number | null {
  const clamp = (t: number) => Math.min(duration, Math.max(0, t));
  switch (key) {
    case "Home":
      return 0;
    case "End":
      return duration;
    case "ArrowRight":
      return forward(1);
    case "PageDown":
      return forward(PAGE_BARS);
    case "ArrowLeft":
      return back(1);
    case "PageUp":
      return back(PAGE_BARS);
    default:
      return null;
  }

  function forward(bars: number): number {
    if (downbeats.length === 0) return clamp(now + FALLBACK_STEP * bars);
    // Bars started so far; the next bar line is the one after them.
    const started = upperBound(downbeats, now + EPS);
    return downbeats[started + bars - 1] ?? duration;
  }

  function back(bars: number): number {
    if (downbeats.length === 0) return clamp(now - FALLBACK_STEP * bars);
    const started = upperBound(downbeats, now + EPS);
    const here = downbeats[started - 1];
    // Partway into a bar, one step back is its own start; at the start it is the previous bar.
    const base = here !== undefined && now - here > BAR_RESTART_AFTER ? started - 1 : started - 2;
    const index = base - (bars - 1);
    return index < 0 ? 0 : (downbeats[index] ?? 0);
  }
}
