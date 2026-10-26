import { describe, expect, it } from "vitest";
import { bucketCount, computePeaks, rebucket } from "./peaks";

describe("computePeaks", () => {
  it("takes min and max per bucket", () => {
    const channel = Float32Array.from([0.1, -0.2, 0.5, -0.5, 0.3, 0.0, -0.8, 0.4]);
    const { data } = computePeaks([channel], 4);
    expect(Array.from(data)).toEqual(
      [-0.2, 0.1, -0.5, 0.5, 0, 0.3, -0.8, 0.4].map((v) => Math.fround(v)),
    );
  });

  it("averages channels", () => {
    const left = Float32Array.from([1, 1]);
    const right = Float32Array.from([-1, 0]);
    const { data } = computePeaks([left, right], 1);
    expect(Array.from(data)).toEqual([0, 0.5]);
  });

  it("scales the loudest peak to full height, capped for near-silence", () => {
    expect(computePeaks([Float32Array.from([0.25, -0.5])], 1).scale).toBeCloseTo(2);
    expect(computePeaks([new Float32Array(8)], 2).scale).toBe(20);
  });

  it("handles more buckets than samples", () => {
    const { data } = computePeaks([Float32Array.from([0.5, -0.5])], 4);
    expect(data).toHaveLength(8);
    expect(Math.max(...data)).toBeCloseTo(0.5);
  });
});

describe("rebucket", () => {
  const peaks = Float32Array.from([-1, 0, -0.5, 0.5, 0, 1, -0.2, 0.2]);
  it("folds buckets into fewer columns keeping extremes", () => {
    expect(Array.from(rebucket(peaks, 2))).toEqual([-1, 0.5, Math.fround(-0.2), 1]);
  });
  it("stretches into more columns", () => {
    const out = rebucket(Float32Array.from([-1, 1]), 3);
    expect(Array.from(out)).toEqual([-1, 1, -1, 1, -1, 1]);
  });
  it("is empty-safe", () => {
    expect(rebucket(new Float32Array(0), 3)).toHaveLength(6);
  });
});

describe("bucketCount", () => {
  it("stays within bounds", () => {
    expect(bucketCount(10)).toBe(2048);
    expect(bucketCount(240)).toBe(6000);
    expect(bucketCount(100000)).toBe(16384);
  });
});
