import { describe, expect, it } from "vitest";
import {
  AMBIGUOUS_KEY_TIP,
  chipFitsLabel,
  chordIndexAt,
  chordsAround,
  keyLabel,
  nextChordIndex,
  type Chord,
} from "./chords";

const chords: Chord[] = [
  { start: 2, end: 4, label: "A" },
  { start: 4, end: 6, label: "E" },
  { start: 8, end: 10, label: "C#m" },
];

describe("chordIndexAt", () => {
  it("is -1 before the first chord", () => expect(chordIndexAt(chords, 1)).toBe(-1));
  it("finds the chord containing the time, start inclusive and end exclusive", () => {
    expect(chordIndexAt(chords, 2)).toBe(0);
    expect(chordIndexAt(chords, 3.9)).toBe(0);
    expect(chordIndexAt(chords, 4)).toBe(1);
  });
  it("is -1 in a gap and after the last chord", () => {
    expect(chordIndexAt(chords, 7)).toBe(-1);
    expect(chordIndexAt(chords, 10)).toBe(-1);
  });
  it("handles no chords", () => expect(chordIndexAt([], 3)).toBe(-1));
});

describe("nextChordIndex", () => {
  it("is the chord after the current one", () => expect(nextChordIndex(chords, 3)).toBe(1));
  it("skips a gap to the next chord", () => expect(nextChordIndex(chords, 7)).toBe(2));
  it("is the first chord before the song starts", () => expect(nextChordIndex(chords, 0)).toBe(0));
  it("is -1 on the last chord", () => expect(nextChordIndex(chords, 9)).toBe(-1));
});

it("chordsAround pairs both", () => {
  expect(chordsAround(chords, 5)).toEqual({ current: 1, next: 2 });
});

describe("keyLabel", () => {
  it("shows only the key when it is certain", () => {
    expect(keyLabel({ key: "A", mode: "major" })).toEqual({
      note: "A",
      mode: "mayor",
      alternative: null,
      tooltip: null,
    });
    expect(keyLabel({ key: "A", mode: "major", alternative: null }).alternative).toBeNull();
  });
  it("adds the alternative and the tooltip when it is doubtful", () => {
    const label = keyLabel({ key: "A", mode: "major", alternative: { key: "E", mode: "major" } });
    expect(label.alternative).toBe("E mayor");
    expect(label.tooltip).toBe(AMBIGUOUS_KEY_TIP);
  });
  it("names minor alternatives and sharps with letter names", () => {
    const label = keyLabel({ key: "E", mode: "major", alternative: { key: "C#", mode: "minor" } });
    expect(label.alternative).toBe("C# menor");
  });
  it("ignores an unknown alternative", () => {
    expect(
      keyLabel({ key: "A", mode: "major", alternative: { key: "unknown", mode: "unknown" } }).alternative,
    ).toBeNull();
  });
});


describe("chipFitsLabel", () => {
  it("fits short labels sooner than long ones", () => {
    expect(chipFitsLabel("A", 20)).toBe(true);
    expect(chipFitsLabel("C#m", 20)).toBe(false);
    expect(chipFitsLabel("C#m", 40)).toBe(true);
  });
  it("never fits in a zero-width track", () => expect(chipFitsLabel("A", 0)).toBe(false));
});
