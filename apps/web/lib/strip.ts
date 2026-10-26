/** The section strip model: repeat grouping, bar numbers and the active section. Pure. */
import type { Section } from "@/lib/api";
import { nearestIndex } from "@/lib/audio/grid";
import { sectionLabel } from "@/lib/processing";

export interface StripSpan {
  start: number;
  end: number;
}

/** One songbook entry; `count > 1` when consecutive sections share a label (`||: CORO :|| x2`). */
export interface StripGroup {
  label: string;
  count: number;
  start: number;
  end: number;
  /** 1-based bar of the first section's nearest downbeat; null without a grid. */
  startBar: number | null;
  spans: StripSpan[];
}

export function buildStrip(
  sections: readonly Pick<Section, "name" | "label" | "start">[],
  downbeats: readonly number[],
  duration: number,
): StripGroup[] {
  const usable = sections.filter((s) => s.start < duration);
  const groups: StripGroup[] = [];
  usable.forEach((section, i) => {
    const end = i + 1 < usable.length ? usable[i + 1].start : duration;
    const span = { start: section.start, end };
    const label = sectionLabel(section);
    const last = groups[groups.length - 1];
    if (last && last.label === label) {
      last.count += 1;
      last.end = end;
      last.spans.push(span);
      return;
    }
    const index = nearestIndex(downbeats, section.start);
    groups.push({
      label,
      count: 1,
      start: section.start,
      end,
      startBar: index >= 0 ? index + 1 : null,
      spans: [span],
    });
  });
  return groups;
}

/** Which group and which repeat contain `time`; null before the first section. */
export function locateActive(
  groups: readonly StripGroup[],
  time: number,
): { group: number; span: number } | null {
  for (let g = 0; g < groups.length; g += 1) {
    const spans = groups[g].spans;
    for (let s = 0; s < spans.length; s += 1) {
      if (time >= spans[s].start && time < spans[s].end) return { group: g, span: s };
    }
  }
  return null;
}

/** One section as drawn: its flat index in the edited list plus its place in a repeat group. */
export interface StripItem {
  index: number;
  group: number;
  label: string;
  /** Group size; > 1 draws the repeat signs on the group's first and last section. */
  count: number;
  first: boolean;
  last: boolean;
  start: number;
  end: number;
}

/** The groups flattened to one entry per section, in song order. */
export function stripItems(groups: readonly StripGroup[]): StripItem[] {
  const items: StripItem[] = [];
  groups.forEach((group, g) => {
    group.spans.forEach((span, s) => {
      items.push({
        index: items.length,
        group: g,
        label: group.label,
        count: group.count,
        first: s === 0,
        last: s === group.spans.length - 1,
        start: span.start,
        end: span.end,
      });
    });
  });
  return items;
}

/** Flat section index of an active `{ group, span }`; null when nothing is active. */
export function flatIndex(
  groups: readonly StripGroup[],
  active: { group: number; span: number } | null,
): number | null {
  if (!active) return null;
  let index = active.span;
  for (let g = 0; g < active.group; g += 1) index += groups[g]?.spans.length ?? 0;
  return index;
}

export interface BarTick {
  bar: number;
  time: number;
  /** A section start, always shown. */
  anchor: boolean;
}

const STEPS = [1, 2, 4, 8, 16, 32, 64, 128];

/**
 * Bar numbers under the strip: every section start, plus regular bars at the smallest step that
 * keeps them `minGapPx` apart, dropping any regular tick that would crowd an anchor.
 */
export function barTicks(
  downbeats: readonly number[],
  duration: number,
  widthPx: number,
  anchorBars: readonly number[],
  minGapPx = 36,
): BarTick[] {
  if (downbeats.length === 0 || duration <= 0 || widthPx <= 0) return [];
  const x = (time: number) => (time / duration) * widthPx;
  const perBar = (x(downbeats[downbeats.length - 1]) - x(downbeats[0])) / Math.max(1, downbeats.length - 1);
  const step = STEPS.find((s) => s * perBar >= minGapPx) ?? STEPS[STEPS.length - 1];
  const anchors = new Set(anchorBars.filter((bar) => bar >= 1 && bar <= downbeats.length));
  const anchorX = [...anchors].map((bar) => x(downbeats[bar - 1]));
  const ticks: BarTick[] = [];
  downbeats.forEach((time, i) => {
    const bar = i + 1;
    if (anchors.has(bar)) {
      ticks.push({ bar, time, anchor: true });
    } else if (i % step === 0 && anchorX.every((ax) => Math.abs(ax - x(time)) >= minGapPx)) {
      ticks.push({ bar, time, anchor: false });
    }
  });
  return ticks;
}

/** Display title from an upload filename: the original name and case, without the extension. */
export function titleFromFilename(filename: string): string {
  return filename.replace(/\.[a-z0-9]{1,5}$/i, "").trim() || filename;
}
