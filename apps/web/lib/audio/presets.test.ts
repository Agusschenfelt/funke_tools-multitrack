import { describe, expect, it } from "vitest";
import { DEFAULT_MIX, type StemMix } from "./mix";
import { applyPresetToMix, detectPreset, presetGains, PRESETS } from "./presets";
import { STEM_ORDER, type StemName } from "./stems";

const FOUR: StemName[] = ["drums", "bass", "other", "vocals"];
const SIX: StemName[] = [...STEM_ORDER];

const fresh = (names: readonly StemName[]) =>
  Object.fromEntries(names.map((n) => [n, { ...DEFAULT_MIX }])) as Record<StemName, StemMix>;

describe("presetGains", () => {
  it("original keeps every stem", () => {
    expect(presetGains("original", SIX)).toEqual({
      drums: 1, bass: 1, piano: 1, guitar: 1, other: 1, vocals: 1,
    });
  });

  it("karaoke drops only the voice, on 4 and 6 stems", () => {
    expect(presetGains("karaoke", FOUR)).toEqual({ drums: 1, bass: 1, other: 1, vocals: 0 });
    expect(presetGains("karaoke", SIX).vocals).toBe(0);
    expect(Object.values(presetGains("karaoke", SIX)).filter((g) => g === 1)).toHaveLength(5);
  });

  it("acapella keeps only the voice", () => {
    expect(presetGains("acapella", FOUR)).toEqual({ drums: 0, bass: 0, other: 0, vocals: 1 });
    expect(Object.values(presetGains("acapella", SIX)).reduce((a, b) => a + b, 0)).toBe(1);
  });

  it("drumless and bassless drop one stem each", () => {
    expect(presetGains("drumless", SIX).drums).toBe(0);
    expect(presetGains("drumless", SIX).bass).toBe(1);
    expect(presetGains("bassless", FOUR).bass).toBe(0);
    expect(presetGains("bassless", FOUR).drums).toBe(1);
  });
});

describe("applyPresetToMix", () => {
  it("sets mutes, clears solos and keeps volume and pan", () => {
    const mix = fresh(FOUR);
    mix.bass = { volume: 0.4, muted: false, solo: true, pan: -0.5 };
    const next = applyPresetToMix("karaoke", mix, FOUR);
    expect(next.vocals.muted).toBe(true);
    expect(next.bass).toEqual({ volume: 0.4, muted: false, solo: false, pan: -0.5 });
    expect(mix.vocals.muted).toBe(false);
  });
});

describe("detectPreset", () => {
  it("starts on original", () => {
    expect(detectPreset(fresh(SIX), SIX)).toBe("original");
  });

  it("recognises every preset on both stem sets", () => {
    for (const names of [FOUR, SIX]) {
      for (const { id } of PRESETS) {
        expect(detectPreset(applyPresetToMix(id, fresh(names), names), names)).toBe(id);
      }
    }
  });

  it("becomes custom after a manual mute or any solo", () => {
    const karaoke = applyPresetToMix("karaoke", fresh(SIX), SIX);
    expect(detectPreset({ ...karaoke, drums: { ...karaoke.drums, muted: true } }, SIX)).toBe("custom");
    expect(detectPreset({ ...karaoke, bass: { ...karaoke.bass, solo: true } }, SIX)).toBe("custom");
  });

  it("ignores volume and pan", () => {
    const mix = fresh(FOUR);
    mix.drums = { ...mix.drums, volume: 0.2, pan: 0.7 };
    expect(detectPreset(mix, FOUR)).toBe("original");
  });

  it("is custom without stems", () => {
    expect(detectPreset({} as Record<StemName, StemMix>, [])).toBe("custom");
  });
});
