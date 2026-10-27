import { describe, expect, it } from "vitest";
import { timeTicks } from "./ruler";

describe("timeTicks", () => {
  it("marks round seconds in m:ss", () => {
    const ticks = timeTicks(60, 1200);
    expect(ticks.slice(0, 3)).toEqual([
      { time: 0, label: "0:00" },
      { time: 5, label: "0:05" },
      { time: 10, label: "0:10" },
    ]);
  });

  it("widens the step until marks fit", () => {
    const ticks = timeTicks(240, 800); // 3.33 px/s -> 30 s clears 56 px
    expect(ticks.map((t) => t.time).slice(0, 4)).toEqual([0, 30, 60, 90]);
    expect(ticks[2].label).toBe("1:00");
    const gaps = ticks.slice(1).map((t, i) => (t.time - ticks[i].time) * (800 / 240));
    expect(Math.min(...gaps)).toBeGreaterThanOrEqual(56);
  });

  it("never marks past the end of the song", () => {
    expect(timeTicks(100, 1000).every((t) => t.time < 100)).toBe(true);
  });

  it("is empty without a width or a song", () => {
    expect(timeTicks(0, 800)).toEqual([]);
    expect(timeTicks(100, 0)).toEqual([]);
  });
});
