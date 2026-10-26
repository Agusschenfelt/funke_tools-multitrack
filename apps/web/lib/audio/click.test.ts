import { describe, expect, it } from "vitest";
import { clickWave } from "./click";

describe("clickWave", () => {
  it("is 60 ms long with an accent at -3 dBFS and a normal click at -7 dBFS", () => {
    const peak = (w: Float32Array) => Math.max(...Array.from(w, Math.abs));
    expect(clickWave(true, 44100)).toHaveLength(2646);
    expect(peak(clickWave(true, 44100))).toBeCloseTo(0.708, 3);
    expect(peak(clickWave(false, 44100))).toBeCloseTo(0.447, 3);
  });

  it("starts at its maximum so the onset is sharp", () => {
    const wave = clickWave(false, 44100);
    expect(wave[0]).toBeCloseTo(0.447, 3);
    expect(Math.abs(wave[wave.length - 1])).toBeLessThan(0.01);
  });
});

describe("clickWave sounds", () => {
  const peak = (w: Float32Array) => Math.max(...Array.from(w, Math.abs));

  it("every sound is 60 ms, normalized to the same accent and normal peaks", () => {
    for (const sound of ["classic", "cowbell", "woodblock", "rimshot"] as const) {
      expect(clickWave(true, 44100, sound)).toHaveLength(2646);
      expect(peak(clickWave(true, 44100, sound))).toBeCloseTo(0.708, 3);
      expect(peak(clickWave(false, 44100, sound))).toBeCloseTo(0.447, 3);
    }
  });

  it("sounds differ from each other and the rimshot is repeatable", () => {
    const classic = clickWave(false, 44100);
    expect(clickWave(false, 44100, "cowbell")).not.toEqual(classic);
    expect(clickWave(false, 44100, "woodblock")).not.toEqual(classic);
    expect(clickWave(false, 44100, "rimshot")).toEqual(clickWave(false, 44100, "rimshot"));
  });
});
