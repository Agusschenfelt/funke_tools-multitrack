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
