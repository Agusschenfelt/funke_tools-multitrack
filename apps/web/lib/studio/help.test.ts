import { describe, expect, it } from "vitest";
import { PRESETS } from "@/lib/audio/presets";
import { AREAS, GESTURES, isHelpKey, LEGEND, SHORTCUTS } from "./help";

describe("help content", () => {
  it("lists the shortcuts the studio really binds", () => {
    const keys = SHORTCUTS.flatMap((s) => s.keys);
    for (const wanted of ["Espacio", "L", "Enter", "Z", "?"]) expect(keys).toContain(wanted);
  });

  it("explains every small mark that the interface shows", () => {
    const marks = LEGEND.map((l) => l.mark);
    for (const wanted of ["M", "S", "L – R", "revisar", "Cuenta"]) expect(marks).toContain(wanted);
    expect(LEGEND.some((l) => /grilla estimada/i.test(l.what))).toBe(true);
  });

  it("mentions dragging the ruler to loop", () => {
    expect(GESTURES.some((g) => /regla/.test(g.how) && /repite/i.test(g.what))).toBe(true);
  });

  it("has no empty text", () => {
    for (const text of [
      ...SHORTCUTS.map((s) => s.what),
      ...GESTURES.flatMap((g) => [g.how, g.what]),
      ...AREAS.flatMap((a) => [a.name, a.what]),
      ...LEGEND.map((l) => l.what),
    ]) {
      expect(text.trim()).not.toBe("");
    }
  });

  it("every quick mix has a one-line hint", () => {
    for (const preset of PRESETS) {
      expect(preset.hint.length).toBeGreaterThan(10);
      expect(preset.hint).not.toContain("\n");
    }
  });
});

describe("isHelpKey", () => {
  const base = { ctrlKey: false, metaKey: false, altKey: false };
  it("accepts ? and nothing else", () => {
    expect(isHelpKey({ key: "?", ...base })).toBe(true);
    expect(isHelpKey({ key: "/", ...base })).toBe(false);
    expect(isHelpKey({ key: "?", ...base, ctrlKey: true })).toBe(false);
  });
});
