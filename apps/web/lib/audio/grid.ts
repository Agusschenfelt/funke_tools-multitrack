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
  /** 1-based; 0 before the first downbeat (the pickup). */
  bar: number;
  /**
   * 1-based, at most the beats per bar. In the pickup it is negative: -1 is the beat right before
   * the first downbeat, -2 the one before that, and 0 means no beat has sounded yet.
   */
  beat: number;
}

export function barPosition(
  time: number,
  beats: readonly number[],
  downbeats: readonly number[],
  perBar: number,
): BarBeat {
  const bars = upperBound(downbeats, time + EPS);
  if (bars === 0) return { bar: 0, beat: pickupBeat(time, beats, downbeats[0]) };
  const barStart = downbeats[bars - 1] - EPS;
  const reached = upperBound(beats, time + EPS) - lowerBound(beats, barStart);
  return { bar: bars, beat: Math.min(perBar, Math.max(1, reached)) };
}

/** Beats left until the first downbeat, as a negative count; 0 when no beat has been reached. */
function pickupBeat(time: number, beats: readonly number[], firstDownbeat: number | undefined): number {
  const reached = upperBound(beats, time + EPS);
  if (reached === 0 || firstDownbeat === undefined) return 0;
  const downbeatIndex = lowerBound(beats, firstDownbeat - EPS);
  return -Math.max(1, downbeatIndex - (reached - 1));
}

/**
 * Readout for the transport. Bars and beats count from 1 (`12:3`). Before the first downbeat
 * (the pickup, or anacrusis) the beats are counted down to it: `1:−2` is two beats before bar 1,
 * `1:−1` is the beat just before it, the way a musician counts "two, one, ONE". Before the first
 * beat there is nothing to count, so it reads `—`.
 */
export function formatBarBeat({ bar, beat }: BarBeat): string {
  if (bar > 0) return `${bar}:${beat}`;
  return beat < 0 ? `1:\u2212${-beat}` : "\u2014";
}

/** `m:ss` (floored, never negative). */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
