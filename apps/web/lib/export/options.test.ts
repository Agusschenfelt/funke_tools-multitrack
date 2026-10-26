import { describe, expect, it } from "vitest";
import { DEFAULT_OPTIONS, parseOptions, readOptions, toApiBody, writeOptions } from "./options";

function memoryStore(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k: string) => data[k] ?? null,
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
  };
}

describe("toApiBody", () => {
  it("sends every field explicitly with the API's snake_case names", () => {
    expect(toApiBody(DEFAULT_OPTIONS)).toEqual({
      destination: "playback",
      count_in_bars: 1,
      click_sound: "classic",
      subdivision: "quarter",
      straight_grid: false,
      sample_rate: 44100,
      include_vocals: false,
      language: "es",
    });
  });

  it("carries a changed choice through", () => {
    const body = toApiBody({
      ...DEFAULT_OPTIONS,
      destination: "daw",
      sampleRate: 48000,
      includeVocals: true,
      countInBars: 2,
      subdivision: "eighth",
      clickSound: "cowbell",
      straightGrid: true,
      language: "en",
    });
    expect(body).toMatchObject({
      destination: "daw",
      sample_rate: 48000,
      include_vocals: true,
      count_in_bars: 2,
      subdivision: "eighth",
      click_sound: "cowbell",
      straight_grid: true,
      language: "en",
    });
  });
});

describe("parseOptions", () => {
  it("falls back to the default for each invalid field and keeps the valid ones", () => {
    expect(parseOptions({ destination: "prime", sampleRate: 48000, countInBars: 3, includeVocals: "yes" })).toEqual({
      ...DEFAULT_OPTIONS,
      sampleRate: 48000,
    });
  });

  it("returns the defaults for junk", () => {
    expect(parseOptions(null)).toEqual(DEFAULT_OPTIONS);
    expect(parseOptions("x")).toEqual(DEFAULT_OPTIONS);
  });
});

describe("remembered options", () => {
  it("round-trips through the store", () => {
    const store = memoryStore();
    const chosen = { ...DEFAULT_OPTIONS, destination: "daw" as const, sampleRate: 48000 as const };
    writeOptions(chosen, store);
    expect(readOptions(store)).toEqual(chosen);
  });

  it("reads defaults from an empty or corrupt store", () => {
    expect(readOptions(memoryStore())).toEqual(DEFAULT_OPTIONS);
    expect(readOptions(memoryStore({ "multitrack:export-options": "{not json" }))).toEqual(DEFAULT_OPTIONS);
  });

  it("never throws when storage is blocked", () => {
    const blocked = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
    };
    expect(readOptions(blocked)).toEqual(DEFAULT_OPTIONS);
    expect(() => writeOptions(DEFAULT_OPTIONS, blocked)).not.toThrow();
  });

  it("works with no storage at all", () => {
    expect(readOptions(null)).toEqual(DEFAULT_OPTIONS);
    expect(() => writeOptions(DEFAULT_OPTIONS, null)).not.toThrow();
  });
});
