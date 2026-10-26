/** What the click and cue schedulers play, and when. Times are original-song seconds. */
import type { SectionName } from "@/lib/api";
import { nearestIndex, lowerBound } from "./grid";

export interface ClickEvent {
  time: number;
  accent: boolean;
}

/** Same tolerance as the server: a beat within 1 ms of a downbeat is that downbeat. */
export const DOWNBEAT_TOLERANCE = 0.001;

export function buildClickEvents(
  beats: readonly number[],
  downbeats: readonly number[],
): ClickEvent[] {
  const out: ClickEvent[] = [];
  let d = 0;
  for (const time of beats) {
    while (d < downbeats.length && downbeats[d] < time - DOWNBEAT_TOLERANCE) d += 1;
    const accent = d < downbeats.length && Math.abs(downbeats[d] - time) <= DOWNBEAT_TOLERANCE;
    out.push({ time, accent });
  }
  return out;
}

/** Events with `from <= time < to` from a time-sorted list (half-open, so windows never repeat one). */
export function eventsInWindow<T extends { time: number }>(
  events: readonly T[],
  from: number,
  to: number,
): T[] {
  if (!(to > from)) return [];
  const out: T[] = [];
  for (let i = lowerBoundBy(events, from); i < events.length && events[i].time < to; i += 1) {
    out.push(events[i]);
  }
  return out;
}

function lowerBoundBy(events: readonly { time: number }[], x: number): number {
  let lo = 0;
  let hi = events.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (events[mid].time < x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Mean beat interval from the first downbeat over two bars (server rule); 0 when unknown. */
export function meanBeatInterval(
  beats: readonly number[],
  firstDownbeat: number,
  perBar: number,
): number {
  if (beats.length < 2) return 0;
  const first = lowerBound(beats, firstDownbeat - 1e-3);
  let window = beats.slice(first, first + 2 * perBar + 1);
  if (window.length < 2 * perBar + 1) window = beats.slice();
  return (window[window.length - 1] - window[0]) / (window.length - 1);
}

export interface CuePlacement {
  time: number;
  name: SectionName;
}

/**
 * Spoken cue for each section, one bar before it (same rule as the server): the section snaps to
 * its nearest downbeat and the cue sits on the previous downbeat. The first downbeat has none, so
 * its cue is one mean bar earlier; a cue that would fall before 0 is skipped.
 */
export function cuePlacements(
  sections: readonly { name: SectionName; start: number }[],
  beats: readonly number[],
  downbeats: readonly number[],
  perBar: number,
): CuePlacement[] {
  if (downbeats.length === 0) return [];
  const bar = meanBeatInterval(beats, downbeats[0], perBar) * perBar;
  const out: CuePlacement[] = [];
  for (const section of sections) {
    const index = nearestIndex(downbeats, section.start);
    const time = index > 0 ? downbeats[index - 1] : downbeats[0] - bar;
    if (time < 0) continue;
    if (out.length > 0 && out[out.length - 1].time === time) continue;
    out.push({ time, name: section.name });
  }
  return out.sort((a, b) => a.time - b.time);
}

/** Frames before the first sample at or above `threshold` (speech onset), as the server trims. */
export function leadingSilenceFrames(samples: ArrayLike<number>, threshold = 0.01): number {
  for (let i = 0; i < samples.length; i += 1) {
    if (Math.abs(samples[i]) >= threshold) return i;
  }
  return 0;
}
