/** Loop A-B: snapping a dragged range to bars, and how the playhead and schedulers cross the wrap. Pure. */
import { formatClock, lowerBound, nearestIndex } from "./grid";

export interface LoopRange {
  /** Seconds, original-song time. */
  start: number;
  end: number;
}

/** Shorter than this is a click, not a loop. */
export const MIN_LOOP_SECONDS = 0.25;

const EPS = 1e-3;

export function inLoop(loop: LoopRange, time: number): boolean {
  return time >= loop.start && time < loop.end;
}

/** Clamps a range to the song; null when what is left is too short to loop. */
export function normalizeLoop(range: LoopRange, duration: number): LoopRange | null {
  const start = Math.max(0, Math.min(range.start, range.end));
  const end = Math.min(duration, Math.max(range.start, range.end));
  return end - start >= MIN_LOOP_SECONDS ? { start, end } : null;
}

/**
 * The range a drag from `a` to `b` selects. With `snap` and a grid both ends land on bar lines
 * (the end may also land on the very end of the song); an empty snapped range grows to one bar.
 * Without snapping the range is exactly what was dragged. Null when it is shorter than a click.
 */
export function snapLoop(
  a: number,
  b: number,
  options: { downbeats: readonly number[]; duration: number; snap: boolean },
): LoopRange | null {
  const { downbeats, duration, snap } = options;
  const lo = Math.max(0, Math.min(a, b));
  const hi = Math.min(duration, Math.max(a, b));
  if (!snap || downbeats.length === 0) return normalizeLoop({ start: lo, end: hi }, duration);

  const last = downbeats[downbeats.length - 1];
  const ends = last < duration - EPS ? [...downbeats, duration] : [...downbeats];
  const start = downbeats[nearestIndex(downbeats, lo)];
  let end = ends[nearestIndex(ends, hi)];
  if (end <= start + EPS) {
    const next = ends[lowerBound(ends, start + EPS)];
    if (next === undefined) return null;
    end = next;
  }
  return normalizeLoop({ start, end }, duration);
}

/** The loop only wraps a run that starts before its end; starting past it plays straight on. */
function wraps(songStart: number, loop: LoopRange | null): loop is LoopRange {
  return loop !== null && songStart < loop.end;
}

/** Song position `elapsed` seconds after a run began at `songStart`, folded through the loop. */
export function songPositionAt(songStart: number, elapsed: number, loop: LoopRange | null): number {
  const e = Math.max(0, elapsed);
  if (!wraps(songStart, loop)) return songStart + e;
  const toEnd = loop.end - songStart;
  if (e < toEnd) return songStart + e;
  return loop.start + ((e - toEnd) % (loop.end - loop.start));
}

/** A stretch of a scheduling window with no wrap inside: song time `from..to`, starting at `at`. */
export interface WindowSegment {
  from: number;
  to: number;
  /** Seconds since the run began at which `from` is heard. */
  at: number;
}

/**
 * Splits the window `[e0, e1)` (seconds since the run began) into stretches of continuous song
 * time. Without a loop that is one stretch; with one, every pass through the wrap starts a new
 * stretch, so clicks and cues on both sides of the wrap keep their place on the clock.
 */
export function windowSegments(
  songStart: number,
  e0: number,
  e1: number,
  loop: LoopRange | null,
): WindowSegment[] {
  if (!(e1 > e0)) return [];
  if (!wraps(songStart, loop)) return [{ from: songStart + e0, to: songStart + e1, at: e0 }];
  const length = loop.end - loop.start;
  const toEnd = loop.end - songStart;
  const out: WindowSegment[] = [];
  let e = e0;
  // Each pass covers at least the rest of a lap, so this ends; the cap only guards float drift.
  for (let guard = 0; e < e1 && guard < (e1 - e0) / length + 4; guard += 1) {
    const from = songPositionAt(songStart, e, loop);
    const lapEnd = e < toEnd ? toEnd : e + (loop.end - from);
    const stop = Math.min(e1, lapEnd);
    out.push({ from, to: from + (stop - e), at: e });
    e = lapEnd - e < 1e-9 ? e + 1e-9 : stop;
  }
  return out;
}

/** "compases 5 a 8" when both ends are bar lines, otherwise the clock range. */
export function loopLabel(loop: LoopRange, downbeats: readonly number[], duration: number): string {
  const start = nearestIndex(downbeats, loop.start);
  const end = nearestIndex(downbeats, loop.end);
  const startOnBar = start >= 0 && Math.abs(downbeats[start] - loop.start) <= EPS;
  const endOnBar = end >= 0 && Math.abs(downbeats[end] - loop.end) <= EPS;
  const atSongEnd = loop.end >= duration - EPS;
  if (startOnBar && (endOnBar || atSongEnd)) {
    const first = start + 1;
    const last = endOnBar ? end : downbeats.length;
    if (last > first) return `compases ${first} a ${last}`;
    if (last === first) return `compás ${first}`;
  }
  return `${formatClock(loop.start)} a ${formatClock(loop.end)}`;
}
