/** Search helpers and the bar:beat position over the analysis grid (original-song seconds). */

/** First index whose value is strictly greater than `x` (== count of values <= x). */
export function upperBound(sorted: readonly number[], x: number): number {
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (sorted[mid] <= x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** First index whose value is >= `x`. */
export function lowerBound(sorted: readonly number[], x: number): number {
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (sorted[mid] < x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Index of the value nearest to `x`; a tie goes to the earlier one (same rule as the server). */
export function nearestIndex(sorted: readonly number[], x: number): number {
  if (sorted.length === 0) return -1;
  const i = lowerBound(sorted, x);
  if (i === 0) return 0;
  if (i === sorted.length) return sorted.length - 1;
  return x - sorted[i - 1] <= sorted[i] - x ? i - 1 : i;
}

export function beatsPerBar(timeSignature: string | undefined): number {
  const n = Number.parseInt((timeSignature ?? "").split("/")[0] ?? "", 10);
  return Number.isFinite(n) && n >= 1 ? n : 4;
}

/** A beat or downbeat this close to the playhead counts as already reached. */
const EPS = 1e-3;

export interface BarBeat {
  /** 1-based; 0 before the first downbeat. */
  bar: number;
  /** 1-based, at most the beats per bar. */
  beat: number;
}

export function barPosition(
  time: number,
  beats: readonly number[],
  downbeats: readonly number[],
  perBar: number,
): BarBeat {
  const bars = upperBound(downbeats, time + EPS);
  const barStart = bars > 0 ? downbeats[bars - 1] - EPS : -Infinity;
  const reached = upperBound(beats, time + EPS) - lowerBound(beats, barStart);
  return { bar: bars, beat: Math.min(perBar, Math.max(1, reached)) };
}

/** `compás:tiempo`, e.g. `12:3`. */
export function formatBarBeat({ bar, beat }: BarBeat): string {
  return `${bar}:${beat}`;
}

/** `m:ss` (floored, never negative). */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
