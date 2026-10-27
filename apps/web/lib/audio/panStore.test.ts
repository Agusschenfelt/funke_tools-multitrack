import { describe, expect, it } from "vitest";
import { loadPans, sanitizePans, savePans } from "./panStore";

function memory(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

const throwing = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
  removeItem: () => {
    throw new Error("blocked");
  },
};

describe("pan store", () => {
  it("round-trips pans per song", () => {
    const store = memory();
    expect(savePans("a", { drums: -0.5, vocals: 0.25 }, store)).toBe(true);
    expect(loadPans("a", store)).toEqual({ drums: -0.5, vocals: 0.25 });
    expect(loadPans("b", store)).toEqual({});
  });

  it("drops the entry once everything is centred", () => {
    const store = memory();
    savePans("a", { bass: 0.3 }, store);
    savePans("a", { bass: 0 }, store);
    expect(store.data.size).toBe(0);
  });

  it("ignores corrupt or hostile stored values", () => {
    expect(loadPans("a", memory({ "studio:pan:a": "{nope" }))).toEqual({});
    expect(sanitizePans({ drums: "x", bass: 9, ghost: 1, other: Number.NaN, vocals: -3 })).toEqual({
      bass: 1,
      vocals: -1,
    });
    expect(sanitizePans(null)).toEqual({});
    expect(sanitizePans([1, 2])).toEqual({});
  });

  it("survives storage that throws or is missing", () => {
    expect(loadPans("a", throwing)).toEqual({});
    expect(savePans("a", { drums: 0.5 }, throwing)).toBe(false);
    expect(loadPans("a", null)).toEqual({});
    expect(savePans("a", { drums: 0.5 }, null)).toBe(false);
  });
});
