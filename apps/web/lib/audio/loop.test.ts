import { describe, expect, it } from "vitest";
import { eventsInWindow } from "./schedule";
import { loopLabel, normalizeLoop, snapLoop, songPositionAt, windowSegments } from "./loop";

// Four-second bars: downbeats at 0, 4, 8, ... 36; the song is 40 s.
const downbeats = Array.from({ length: 10 }, (_, i) => i * 4);
const options = { downbeats, duration: 40, snap: true };

describe("snapLoop", () => {
  it("snaps both ends to the nearest bar line", () => {
    expect(snapLoop(9.1, 18.5, options)).toEqual({ start: 8, end: 20 });
  });

  it("is order independent", () => {
    expect(snapLoop(18.5, 9.1, options)).toEqual({ start: 8, end: 20 });
  });

  it("grows an empty snapped range to one bar", () => {
    expect(snapLoop(8.4, 8.9, options)).toEqual({ start: 8, end: 12 });
    expect(snapLoop(11.7, 12.2, options)).toEqual({ start: 12, end: 16 });
  });

  it("lets the end land on the end of the song", () => {
    expect(snapLoop(30, 39.9, options)).toEqual({ start: 28, end: 40 });
  });

  it("closes the last bar on the end of the song", () => {
    expect(snapLoop(39.5, 40, options)).toEqual({ start: 36, end: 40 });
  });

  it("gives up when the grid leaves no bar after the start", () => {
    expect(snapLoop(7, 8, { downbeats: [8], duration: 8, snap: true })).toBeNull();
  });

  it("keeps the exact range when snapping is off (Alt)", () => {
    expect(snapLoop(9.1, 18.5, { ...options, snap: false })).toEqual({ start: 9.1, end: 18.5 });
  });

  it("does not snap without a grid", () => {
    expect(snapLoop(3, 7, { downbeats: [], duration: 40, snap: true })).toEqual({ start: 3, end: 7 });
  });

  it("treats a tiny unsnapped drag as no loop and clamps to the song", () => {
    expect(snapLoop(5, 5.1, { ...options, snap: false })).toBeNull();
    expect(snapLoop(-5, 99, { ...options, snap: false })).toEqual({ start: 0, end: 40 });
  });

  it("normalizeLoop orders and clamps", () => {
    expect(normalizeLoop({ start: 12, end: 3 }, 10)).toEqual({ start: 3, end: 10 });
    expect(normalizeLoop({ start: 3, end: 3.1 }, 10)).toBeNull();
  });
});

describe("songPositionAt", () => {
  const loop = { start: 10, end: 12 };

  it("is a straight line without a loop", () => {
    expect(songPositionAt(5, 3, null)).toBe(8);
  });

  it("runs on until the loop end, then wraps to its start", () => {
    expect(songPositionAt(11, 0.5, loop)).toBe(11.5);
    expect(songPositionAt(11, 1, loop)).toBe(10);
    expect(songPositionAt(11, 1.5, loop)).toBeCloseTo(10.5);
    expect(songPositionAt(11, 3.25, loop)).toBeCloseTo(10.25);
  });

  it("enters the loop from before it", () => {
    expect(songPositionAt(8, 3, loop)).toBe(11);
    expect(songPositionAt(8, 5, loop)).toBeCloseTo(11, 6);
  });

  it("plays straight on when the run starts past the loop end", () => {
    expect(songPositionAt(20, 5, loop)).toBe(25);
  });
});

describe("windowSegments", () => {
  const loop = { start: 10, end: 12 };

  it("is one segment away from the wrap", () => {
    expect(windowSegments(11, 0, 0.5, loop)).toEqual([{ from: 11, to: 11.5, at: 0 }]);
    expect(windowSegments(11, 0, 0.5, null)).toEqual([{ from: 11, to: 11.5, at: 0 }]);
  });

  it("splits a window that crosses the wrap", () => {
    const segments = windowSegments(11, 0.5, 1.5, loop);
    expect(segments).toHaveLength(2);
    expect(segments[0]).toEqual({ from: 11.5, to: 12, at: 0.5 });
    expect(segments[1].from).toBe(10);
    expect(segments[1].to).toBeCloseTo(10.5);
    expect(segments[1].at).toBe(1);
  });

  it("covers several laps of a short loop", () => {
    const segments = windowSegments(10, 0, 5, { start: 10, end: 11 });
    expect(segments).toHaveLength(5);
    expect(segments.map((s) => s.at)).toEqual([0, 1, 2, 3, 4]);
    expect(segments.every((s) => Math.abs(s.to - s.from - 1) < 1e-9)).toBe(true);
  });

  it("returns nothing for an empty window", () => {
    expect(windowSegments(11, 1, 1, loop)).toEqual([]);
  });

  it("places clicks on both sides of the wrap at the right time on the clock", () => {
    const clicks = [10.2, 10.7, 11.2, 11.7].map((time) => ({ time }));
    const heard: number[] = [];
    // A 2 s loop played from 11.0; the clock window 0.5..2.0 spans the wrap at 1.0.
    for (const segment of windowSegments(11, 0.5, 2, loop)) {
      for (const click of eventsInWindow(clicks, segment.from, segment.to)) {
        heard.push(segment.at + (click.time - segment.from));
      }
    }
    // 11.2 -> 0.2 is before the window; 11.7 -> 0.7; wrap; 10.2 -> 1.2; 10.7 -> 1.7.
    expect(heard.map((t) => Math.round(t * 1000) / 1000)).toEqual([0.7, 1.2, 1.7]);
  });

  it("agrees with songPositionAt at every segment start", () => {
    for (const segment of windowSegments(10.7, 0, 9, loop)) {
      expect(songPositionAt(10.7, segment.at, loop)).toBeCloseTo(segment.from, 6);
    }
  });
});

describe("loopLabel", () => {
  it("names bars when both ends are bar lines", () => {
    expect(loopLabel({ start: 16, end: 32 }, downbeats, 40)).toBe("compases 5 a 8");
    expect(loopLabel({ start: 16, end: 20 }, downbeats, 40)).toBe("compás 5");
    expect(loopLabel({ start: 28, end: 40 }, downbeats, 40)).toBe("compases 8 a 10");
  });

  it("falls back to the clock for free ranges", () => {
    expect(loopLabel({ start: 9.1, end: 78.5 }, downbeats, 100)).toBe("0:09 a 1:18");
  });
});
