import { describe, expect, it } from "vitest";
import { DEFAULT_MIX, stemGains, type StemMix } from "./mix";

const mix = (over: Partial<Record<"a" | "b" | "c", Partial<StemMix>>> = {}) => ({
  a: { ...DEFAULT_MIX, ...over.a },
  b: { ...DEFAULT_MIX, ...over.b },
  c: { ...DEFAULT_MIX, ...over.c },
});

describe("stemGains", () => {
  it("plays every stem at its volume by default", () => {
    expect(stemGains(mix({ b: { volume: 0.4 } }))).toEqual({ a: 1, b: 0.4, c: 1 });
  });

  it("silences muted stems", () => {
    expect(stemGains(mix({ a: { muted: true } }))).toEqual({ a: 0, b: 1, c: 1 });
  });

  it("with any solo only soloed stems sound", () => {
    expect(stemGains(mix({ b: { solo: true } }))).toEqual({ a: 0, b: 1, c: 0 });
    expect(stemGains(mix({ a: { solo: true }, c: { solo: true, volume: 0.5 } }))).toEqual({
      a: 1,
      b: 0,
      c: 0.5,
    });
  });

  it("lets solo override mute", () => {
    expect(stemGains(mix({ a: { muted: true, solo: true } })).a).toBe(1);
  });

  it("clamps volume to 0..1", () => {
    expect(stemGains(mix({ a: { volume: 3 }, b: { volume: -1 }, c: { volume: NaN } }))).toEqual({
      a: 1,
      b: 0,
      c: 0,
    });
  });
});
