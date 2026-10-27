/** Chord lane and key label logic. Pure. */

export interface Chord {
  start: number;
  end: number;
  /** Sharps only: "A", "C#m". */
  label: string;
}

export interface KeyShape {
  key: string;
  mode: string;
  alternative?: { key: string; mode: string } | null;
}

export const AMBIGUOUS_KEY_TIP = "Tonalidad dudosa: el tema podría estar en cualquiera de las dos";

/**
 * Index of the chord sounding at `time`, or -1 before the first chord and in a gap between chords.
 * Chords are sorted and do not overlap.
 */
export function chordIndexAt(chords: readonly Chord[], time: number): number {
  let lo = 0;
  let hi = chords.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (chords[mid].start <= time) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found >= 0 && time < chords[found].end ? found : -1;
}

/** Index of the first chord that starts after `time`, or -1 when none is left. */
export function nextChordIndex(chords: readonly Chord[], time: number): number {
  let lo = 0;
  let hi = chords.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (chords[mid].start > time) hi = mid;
    else lo = mid + 1;
  }
  return lo < chords.length ? lo : -1;
}

/** Chord lane readouts for the playhead: the chord now and the next one. */
export function chordsAround(
  chords: readonly Chord[],
  time: number,
): { current: number; next: number } {
  return { current: chordIndexAt(chords, time), next: nextChordIndex(chords, time) };
}

const SOLFEGE: Record<string, string> = {
  C: "Do",
  D: "Re",
  E: "Mi",
  F: "Fa",
  G: "Sol",
  A: "La",
  B: "Si",
};

/** "E" -> "Mi", "C#" -> "Do#". Anything unknown is returned as it came. */
export function solfegeName(note: string): string {
  const base = SOLFEGE[note.charAt(0)];
  return base ? base + note.slice(1) : note;
}

function modeWord(mode: string): string {
  const m = mode.toLowerCase();
  if (m === "major") return "mayor";
  if (m === "minor") return "menor";
  return mode;
}

export interface KeyLabel {
  /** Letter name as in the chord sheet: "A". */
  note: string;
  mode: string;
  /** "Mi mayor" when the key is doubtful; null otherwise. */
  alternative: string | null;
  /** Tooltip for a doubtful key. */
  tooltip: string | null;
}

/** What the song bar shows for a key: "A mayor" and, when doubtful, "(o Mi mayor)". */
export function keyLabel(key: KeyShape): KeyLabel {
  const alt = key.alternative;
  const doubtful = Boolean(alt && alt.key && alt.key !== "unknown");
  return {
    note: key.key,
    mode: modeWord(key.mode),
    alternative: alt && doubtful ? `${solfegeName(alt.key)} ${modeWord(alt.mode)}` : null,
    tooltip: doubtful ? AMBIGUOUS_KEY_TIP : null,
  };
}

/** Approximate width of one chord-sheet mono glyph at the chip's font size, in px. */
const CHIP_GLYPH_PX = 7.5;
const CHIP_PADDING_PX = 8;

/** Whether a chip `widthPx` wide can show its label whole; narrower ones stay as a tick. */
export function chipFitsLabel(label: string, widthPx: number): boolean {
  return widthPx >= label.length * CHIP_GLYPH_PX + CHIP_PADDING_PX;
}
