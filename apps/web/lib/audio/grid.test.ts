import { describe, expect, it } from "vitest";
import {
  barPosition,
  beatsPerBar,
  formatBarBeat,
  formatClock,
  nearestIndex,
  upperBound,
} from "./grid";

// 120 BPM in 4/4: beats every 0.5 s, first downbeat at 0.5 s (a 0.5 s pickup), then every 2 s.
const beats = Array.from({ length: 40 }, (_, i) => i * 0.5);
const downbeats = [0.5, 2.5, 4.5, 6.5, 8.5];

describe("barPosition", () => {
  const at = (t: number) => formatBarBeat(barPosition(t, beats, downbeats, 4));

  it("reads bar 1 beat 1 on the first downbeat", () => {
    expect(at(0.5)).toBe("1:1");
  });
  it("counts beats inside the bar", () => {
    expect(at(1.0)).toBe("1:2");
    expect(at(2.0)).toBe("1:4");
    expect(at(2.49)).toBe("1:4");
  });
  it("moves to the next bar on its downbeat", () => {
    expect(at(2.5)).toBe("2:1");
    expect(at(3.1)).toBe("2:2");
  });
  it("reads the pickup as a count-in until the first downbeat", () => {
    // Beats at 0 and 0.5, first downbeat at 0.5: one beat of pickup.
    expect(at(0)).toBe("Cuenta");
    expect(at(0.2)).toBe("Cuenta");
    expect(at(0.49)).toBe("Cuenta");
  });
  it("keeps reading the count-in through a longer pickup", () => {
    const late = [1.5];
    const grid = (t: number) => formatBarBeat(barPosition(t, beats, late, 4));
    expect(grid(0)).toBe("Cuenta");
    expect(grid(0.5)).toBe("Cuenta");
    expect(grid(1.0)).toBe("Cuenta");
    expect(grid(1.5)).toBe("1:1");
  });
  it("shows a dash before the first beat, and never 0:1", () => {
    const offset = [0.5, 1, 1.5, 2];
    expect(formatBarBeat(barPosition(0.2, offset, [1.5], 4))).toBe("\u2014");
    expect(formatBarBeat(barPosition(0.2, [], [], 4))).toBe("\u2014");
    expect(at(0)).not.toBe("0:1");
  });
  it("reports bar 0 with a negative beat in the model", () => {
    expect(barPosition(0.2, beats, downbeats, 4)).toEqual({ bar: 0, beat: -1 });
  });
  it("caps the beat at the beats per bar", () => {
    expect(barPosition(30, beats, [0.5], 4).beat).toBe(4);
  });
  it("tolerates a playhead a hair before the downbeat", () => {
    expect(at(2.4995)).toBe("2:1");
  });
});

describe("helpers", () => {
  it("formats the clock", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(65.9)).toBe("1:05");
    expect(formatClock(-3)).toBe("0:00");
  });
  it("reads beats per bar with a 4 fallback", () => {
    expect(beatsPerBar("3/4")).toBe(3);
    expect(beatsPerBar("6/8")).toBe(6);
    expect(beatsPerBar(undefined)).toBe(4);
    expect(beatsPerBar("x")).toBe(4);
  });
  it("finds the nearest index, ties to the earlier", () => {
    expect(nearestIndex([0, 2, 4], 1)).toBe(0);
    expect(nearestIndex([0, 2, 4], 1.01)).toBe(1);
    expect(nearestIndex([0, 2, 4], 99)).toBe(2);
    expect(nearestIndex([], 1)).toBe(-1);
  });
  it("upperBound counts values <= x", () => {
    expect(upperBound([1, 2, 3], 2)).toBe(2);
  });
});
