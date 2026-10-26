import { describe, expect, it } from "vitest";
import {
  buildClickEvents,
  cuePlacements,
  eventsInWindow,
  leadingSilenceFrames,
  meanBeatInterval,
} from "./schedule";

const beats = Array.from({ length: 24 }, (_, i) => i * 0.5);
const downbeats = [0.5, 2.5, 4.5, 6.5, 8.5];

describe("click schedule", () => {
  const events = buildClickEvents(beats, downbeats);

  it("accents downbeats only", () => {
    expect(events.filter((e) => e.accent).map((e) => e.time)).toEqual([0.5, 2.5, 4.5, 6.5, 8.5]);
    expect(events).toHaveLength(beats.length);
  });

  it("accents a beat within 1 ms of a downbeat", () => {
    const e = buildClickEvents([0.5004, 1], [0.5]);
    expect(e.map((x) => x.accent)).toEqual([true, false]);
  });

  it("returns the beats inside a lookahead window, half-open", () => {
    const got = eventsInWindow(events, 1.0, 2.5);
    expect(got.map((e) => e.time)).toEqual([1.0, 1.5, 2.0]);
    // The next window starts where the last ended: no beat repeats or is missed.
    const next = eventsInWindow(events, 2.5, 3.5);
    expect(next.map((e) => e.time)).toEqual([2.5, 3.0]);
    expect(next[0].accent).toBe(true);
  });

  it("is empty for an empty or inverted window", () => {
    expect(eventsInWindow(events, 3, 3)).toEqual([]);
    expect(eventsInWindow(events, 5, 4)).toEqual([]);
    expect(eventsInWindow(events, 100, 101)).toEqual([]);
  });
});

describe("cue placement", () => {
  it("measures the bar from the first downbeat", () => {
    expect(meanBeatInterval(beats, 0.5, 4)).toBeCloseTo(0.5);
  });

  it("puts a cue on the downbeat before the section's", () => {
    const cues = cuePlacements(
      [
        { name: "verse", start: 2.6 },
        { name: "chorus", start: 6.4 },
      ],
      beats,
      downbeats,
      4,
    );
    expect(cues).toEqual([
      { time: 0.5, name: "verse" },
      { time: 4.5, name: "chorus" },
    ]);
  });

  it("falls back to one bar before the first downbeat, or skips it before 0", () => {
    // First downbeat at 2.5: one bar (2 s) earlier is 0.5.
    expect(cuePlacements([{ name: "intro", start: 2.5 }], beats, [2.5, 4.5], 4)).toEqual([
      { time: 0.5, name: "intro" },
    ]);
    // First downbeat at 0.5: the cue would land at -1.5, so none.
    expect(cuePlacements([{ name: "intro", start: 0.5 }], beats, downbeats, 4)).toEqual([]);
  });

  it("is empty without a grid", () => {
    expect(cuePlacements([{ name: "verse", start: 1 }], [], [], 4)).toEqual([]);
  });
});

describe("leadingSilenceFrames", () => {
  it("counts frames before the speech onset", () => {
    expect(leadingSilenceFrames([0, 0.001, 0.005, 0.2, 0.5])).toBe(3);
    expect(leadingSilenceFrames([0, 0, 0])).toBe(0);
  });
});
