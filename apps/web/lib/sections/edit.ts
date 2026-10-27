/**
 * Section editing model: snapping to bar lines, boundary moves, split, merge, rename and the
 * API shape on the way out. Pure; every edit returns a new array or null when it is refused or
 * changes nothing. Section starts are seconds in the original song, as in the API.
 */
import type { Section, SectionName, Sections } from "@/lib/api";
import { nearestIndex } from "@/lib/audio/grid";

/** The vocabulary in the order a song usually runs, with the Spanish names shown in the editor. */
export const SECTION_OPTIONS: readonly { value: SectionName; label: string }[] = [
  { value: "intro", label: "Intro" },
  { value: "verse", label: "Estrofa" },
  { value: "verse_2", label: "Estrofa 2" },
  { value: "pre_chorus", label: "Pre-coro" },
  { value: "chorus", label: "Coro" },
  { value: "bridge", label: "Puente" },
  { value: "solo", label: "Solo" },
  { value: "instrumental", label: "Instrumental" },
  { value: "break", label: "Break" },
  { value: "outro", label: "Final" },
  { value: "tag", label: "Tag" },
];

/** Confidence given to a section a person touched: it no longer needs a second look. */
const CONFIRMED = 1;
/** Detected labels below this are shown as "revisar". */
export const REVIEW_BELOW = 0.5;

export interface EditResult {
  sections: Section[];
  /** The section to keep selected afterwards. */
  index: number;
}

/** 1-based bar whose line is nearest to `time`; null without a grid. */
export function barAt(downbeats: readonly number[], time: number): number | null {
  const index = nearestIndex(downbeats, time);
  return index < 0 ? null : index + 1;
}

/** Time of the nearest bar line to `time`; null without a grid. */
export function snapToDownbeat(downbeats: readonly number[], time: number): number | null {
  const index = nearestIndex(downbeats, time);
  return index < 0 ? null : downbeats[index];
}

function confirmed(section: Section): Section {
  return { ...section, confidence: CONFIRMED };
}

function strictlyIncreasing(sections: readonly Section[]): boolean {
  return sections.every((s, i) => i === 0 || s.start > sections[i - 1].start);
}

/**
 * Moves the edge that starts section `index` (the first section has no edge) to the bar line
 * nearest `time`. It stays at least one bar away from both neighbours; null when nothing moves.
 */
export function moveBoundary(
  sections: readonly Section[],
  index: number,
  time: number,
  downbeats: readonly number[],
): EditResult | null {
  if (index < 1 || index >= sections.length || downbeats.length === 0) return null;
  const lowest = nearestIndex(downbeats, sections[index - 1].start) + 1;
  const highest =
    index + 1 < sections.length
      ? nearestIndex(downbeats, sections[index + 1].start) - 1
      : downbeats.length - 1;
  if (lowest > highest) return null;
  const target = Math.min(highest, Math.max(lowest, nearestIndex(downbeats, time)));
  const start = downbeats[target];
  if (start === sections[index].start) return null;
  const next = sections.map((s) => ({ ...s }));
  next[index - 1] = confirmed(next[index - 1]);
  next[index] = { ...confirmed(next[index]), start };
  return strictlyIncreasing(next) ? { sections: next, index } : null;
}

/** Moves the edge by whole bars (negative is earlier). */
export function nudgeBoundary(
  sections: readonly Section[],
  index: number,
  bars: number,
  downbeats: readonly number[],
): EditResult | null {
  if (index < 1 || index >= sections.length || downbeats.length === 0) return null;
  const current = nearestIndex(downbeats, sections[index].start);
  const target = downbeats[current + bars];
  return target === undefined ? null : moveBoundary(sections, index, target, downbeats);
}

/** Cuts the section under `time` at the nearest bar line; both halves keep at least one bar. */
export function splitAt(
  sections: readonly Section[],
  time: number,
  downbeats: readonly number[],
): EditResult | null {
  if (downbeats.length === 0) return null;
  let k = -1;
  sections.forEach((s, i) => {
    if (s.start <= time) k = i;
  });
  if (k < 0) return null;
  const from = nearestIndex(downbeats, sections[k].start);
  const cut = nearestIndex(downbeats, time);
  const to = k + 1 < sections.length ? nearestIndex(downbeats, sections[k + 1].start) : downbeats.length;
  if (cut - from < 1 || to - cut < 1) return null;
  const half: Section = { ...confirmed(sections[k]), start: downbeats[cut] };
  const next = [...sections.slice(0, k + 1), half, ...sections.slice(k + 1)];
  return strictlyIncreasing(next) ? { sections: next, index: k + 1 } : null;
}

/**
 * Folds section `index` into a neighbour, which keeps its own name. Merging into the previous
 * one extends it; merging into the next one pulls its start back. The last section never goes.
 */
export function mergeInto(
  sections: readonly Section[],
  index: number,
  side: "prev" | "next",
): EditResult | null {
  if (sections.length < 2 || index < 0 || index >= sections.length) return null;
  if (side === "prev") {
    if (index < 1) return null;
    const next = sections.filter((_, i) => i !== index);
    next[index - 1] = confirmed(next[index - 1]);
    return { sections: next, index: index - 1 };
  }
  if (index + 1 >= sections.length) return null;
  const next = sections.filter((_, i) => i !== index);
  next[index] = { ...confirmed(next[index]), start: sections[index].start };
  return { sections: next, index };
}

/** Sets the name and the optional free label; null when it is already so. */
export function renameSection(
  sections: readonly Section[],
  index: number,
  name: SectionName,
  label: string | null,
): EditResult | null {
  const current = sections[index];
  if (!current || !SECTION_OPTIONS.some((o) => o.value === name)) return null;
  const clean = label?.trim() || null;
  if (current.name === name && (current.label?.trim() || null) === clean) return null;
  const next = sections.map((s) => ({ ...s }));
  next[index] = { ...confirmed(current), name, label: clean };
  return { sections: next, index };
}

/** Whether a section shows the "revisar" marker: a weak or missing detected confidence. */
export function needsReview(section: Section, editedOnServer: boolean): boolean {
  if (typeof section.confidence === "number") return section.confidence < REVIEW_BELOW;
  return !editedOnServer;
}

function tidy(section: Section): Section {
  return {
    name: section.name,
    start: section.start,
    label: section.label?.trim() || null,
    confidence: section.confidence ?? null,
    cluster: section.cluster ?? null,
  };
}

/** The PUT body: sorted by start, unique starts (a later duplicate is dropped), finite seconds. */
export function serializeSections(sections: readonly Section[], source: string | null = null): Sections {
  const sorted = sections
    .filter((s) => Number.isFinite(s.start) && s.start >= 0)
    .map(tidy)
    .sort((a, b) => a.start - b.start);
  const unique = sorted.filter((s, i) => i === 0 || s.start !== sorted[i - 1].start);
  return { source, sections: unique };
}

export function isDirty(current: readonly Section[], baseline: readonly Section[]): boolean {
  return (
    JSON.stringify(serializeSections(current).sections) !==
    JSON.stringify(serializeSections(baseline).sections)
  );
}

/** Undo/redo for one editing session. */
export interface History<T> {
  past: readonly T[];
  present: T;
  future: readonly T[];
}

const HISTORY_LIMIT = 100;

export function createHistory<T>(present: T): History<T> {
  return { past: [], present, future: [] };
}

export function commit<T>(history: History<T>, next: T): History<T> {
  if (Object.is(next, history.present)) return history;
  return {
    past: [...history.past, history.present].slice(-HISTORY_LIMIT),
    present: next,
    future: [],
  };
}

export function undo<T>(history: History<T>): History<T> {
  const { past } = history;
  if (past.length === 0) return history;
  return {
    past: past.slice(0, -1),
    present: past[past.length - 1],
    future: [history.present, ...history.future],
  };
}

export function redo<T>(history: History<T>): History<T> {
  const [next, ...future] = history.future;
  if (next === undefined) return history;
  return { past: [...history.past, history.present], present: next, future };
}
