/** The time ruler: m:ss marks at a round step, thinned to fit the width. Pure. */
import { formatClock } from "./grid";

export interface TimeTick {
  time: number;
  label: string;
}

/** Seconds between marks, smallest first. */
const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600];

/** Closest two time marks may sit; wide enough for "10:30" in the mono face. */
export const TIME_MIN_GAP_PX = 56;

export function timeTicks(duration: number, widthPx: number, minGapPx = TIME_MIN_GAP_PX): TimeTick[] {
  if (!(duration > 0) || !(widthPx > 0)) return [];
  const pxPerSecond = widthPx / duration;
  const step = STEPS.find((s) => s * pxPerSecond >= minGapPx) ?? STEPS[STEPS.length - 1];
  const ticks: TimeTick[] = [];
  for (let time = 0; time < duration; time += step) ticks.push({ time, label: formatClock(time) });
  return ticks;
}
