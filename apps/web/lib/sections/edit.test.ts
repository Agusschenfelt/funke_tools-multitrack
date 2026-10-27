import { describe, expect, it } from "vitest";
import type { Section } from "@/lib/api";
import {
  barAt,
  commit,
  createHistory,
  isDirty,
  mergeInto,
  moveBoundary,
  needsReview,
  nudgeBoundary,
  redo,
  renameSection,
  serializeSections,
  snapToDownbeat,
  splitAt,
  undo,
} from "./edit";

// 16 bars of 2 s starting at 0.5.
const downbeats = Array.from({ length: 16 }, (_, i) => 0.5 + i * 2);
const base: Section[] = [
  { name: "intro", start: 0.5, confidence: 0.3, cluster: 0 },
  { name: "verse", start: 8.5, confidence: 0.9, cluster: 1 },
  { name: "chorus", start: 16.5, confidence: 0.2, cluster: 2 },
];

describe("snapping", () => {
  it("finds the nearest bar line and its number", () => {
    expect(snapToDownbeat(downbeats, 9.4)).toBe(8.5);
    expect(snapToDownbeat(downbeats, 9.6)).toBe(10.5);
    expect(barAt(downbeats, 8.6)).toBe(5);
    expect(barAt([], 3)).toBeNull();
    expect(snapToDownbeat([], 3)).toBeNull();
  });
});

describe("moveBoundary", () => {
  it("snaps to the nearest bar and confirms both sides", () => {
    const result = moveBoundary(base, 1, 11.3, downbeats)!;
    expect(result.sections[1].start).toBe(10.5);
    expect(result.sections[0].confidence).toBe(1);
    expect(result.sections[1].confidence).toBe(1);
    expect(result.sections[2].confidence).toBe(0.2);
    expect(base[1].start).toBe(8.5);
  });

  it("never crosses a neighbour and keeps one bar", () => {
    expect(moveBoundary(base, 1, 100, downbeats)!.sections[1].start).toBe(14.5);
    expect(moveBoundary(base, 1, -5, downbeats)!.sections[1].start).toBe(2.5);
  });

  it("refuses the first section, bad indexes, no grid and no-ops", () => {
    expect(moveBoundary(base, 0, 4, downbeats)).toBeNull();
    expect(moveBoundary(base, 3, 4, downbeats)).toBeNull();
    expect(moveBoundary(base, 1, 4, [])).toBeNull();
    expect(moveBoundary(base, 1, 8.6, downbeats)).toBeNull();
  });

  it("limits the last section's edge to the last bar", () => {
    expect(moveBoundary(base, 2, 999, downbeats)!.sections[2].start).toBe(30.5);
  });

  it("is refused when the neighbours leave no room", () => {
    const tight: Section[] = [
      { name: "intro", start: 0.5 },
      { name: "verse", start: 2.5 },
      { name: "chorus", start: 4.5 },
    ];
    expect(moveBoundary(tight, 1, 3.5, downbeats)).toBeNull();
  });
});

describe("nudgeBoundary", () => {
  it("moves by whole bars and stops at the limits", () => {
    expect(nudgeBoundary(base, 1, 1, downbeats)!.sections[1].start).toBe(10.5);
    expect(nudgeBoundary(base, 1, -1, downbeats)!.sections[1].start).toBe(6.5);
    const edge: Section[] = [
      { name: "intro", start: 0.5 },
      { name: "verse", start: 2.5 },
    ];
    expect(nudgeBoundary(edge, 1, -1, downbeats)).toBeNull();
    expect(nudgeBoundary(base, 0, 1, downbeats)).toBeNull();
  });
});

describe("splitAt", () => {
  it("cuts at the nearest bar and selects the new half", () => {
    const result = splitAt(base, 11.9, downbeats)!;
    expect(result.index).toBe(2);
    expect(result.sections.map((s) => s.start)).toEqual([0.5, 8.5, 12.5, 16.5]);
    expect(result.sections[2].name).toBe("verse");
    expect(result.sections[2].confidence).toBe(1);
  });

  it("keeps a bar on each side", () => {
    expect(splitAt(base, 8.7, downbeats)).toBeNull();
    expect(splitAt(base, 16.4, downbeats)).toBeNull();
    expect(splitAt(base, 0.2, downbeats)).toBeNull();
    expect(splitAt(base, 4, [])).toBeNull();
  });

  it("can split the last section", () => {
    expect(splitAt(base, 24.4, downbeats)!.sections.map((s) => s.start)).toEqual([0.5, 8.5, 16.5, 24.5]);
  });
});

describe("mergeInto", () => {
  it("folds a section into the previous one", () => {
    const result = mergeInto(base, 1, "prev")!;
    expect(result.sections.map((s) => s.name)).toEqual(["intro", "chorus"]);
    expect(result.index).toBe(0);
  });

  it("folds a section into the next one, pulling its start back", () => {
    const result = mergeInto(base, 1, "next")!;
    expect(result.sections.map((s) => [s.name, s.start])).toEqual([
      ["intro", 0.5],
      ["chorus", 8.5],
    ]);
    expect(result.index).toBe(1);
  });

  it("keeps the first start when the first section is folded forward", () => {
    expect(mergeInto(base, 0, "next")!.sections[0].start).toBe(0.5);
  });

  it("refuses impossible merges", () => {
    expect(mergeInto(base, 0, "prev")).toBeNull();
    expect(mergeInto(base, 2, "next")).toBeNull();
    expect(mergeInto([base[0]], 0, "next")).toBeNull();
  });
});

describe("renameSection", () => {
  it("sets the name and a trimmed label, and confirms the section", () => {
    const result = renameSection(base, 0, "verse", "  Estrofa A ")!;
    expect(result.sections[0]).toMatchObject({ name: "verse", label: "Estrofa A", confidence: 1 });
  });

  it("clears an empty label and ignores no-ops and unknown names", () => {
    expect(renameSection(base, 0, "intro", "  ")).toBeNull();
    expect(renameSection(base, 0, "nope" as never, null)).toBeNull();
    expect(renameSection(base, 9, "intro", null)).toBeNull();
    expect(renameSection([{ ...base[0], label: "x" }], 0, "intro", "")!.sections[0].label).toBeNull();
  });
});

describe("needsReview", () => {
  it("flags weak or missing detected confidence, not edited sections", () => {
    expect(needsReview({ name: "verse", start: 0, confidence: 0.49 }, false)).toBe(true);
    expect(needsReview({ name: "verse", start: 0, confidence: 0.5 }, false)).toBe(false);
    expect(needsReview({ name: "verse", start: 0 }, false)).toBe(true);
    expect(needsReview({ name: "verse", start: 0 }, true)).toBe(false);
    expect(needsReview({ name: "verse", start: 0, confidence: 1 }, false)).toBe(false);
  });
});

describe("serializeSections and isDirty", () => {
  it("sorts, drops duplicate starts and normalizes labels", () => {
    const body = serializeSections(
      [
        { name: "chorus", start: 10, label: " " },
        { name: "intro", start: 0 },
        { name: "verse", start: 10 },
        { name: "tag", start: Number.NaN },
      ],
      "t.wav",
    );
    expect(body.source).toBe("t.wav");
    expect(body.sections.map((s) => [s.name, s.start, s.label])).toEqual([
      ["intro", 0, null],
      ["chorus", 10, null],
    ]);
  });

  it("is dirty only when the payload differs", () => {
    expect(isDirty(base, base.map((s) => ({ ...s })))).toBe(false);
    expect(isDirty(base, [...base].reverse())).toBe(false);
    expect(isDirty(moveBoundary(base, 1, 11, downbeats)!.sections, base)).toBe(true);
    expect(isDirty([{ ...base[0], label: "" }], [{ ...base[0], label: null }])).toBe(false);
  });
});

describe("history", () => {
  it("undoes and redoes, clears redo on a new edit and ignores same-reference commits", () => {
    let h = createHistory(1);
    h = commit(h, 2);
    h = commit(h, 3);
    expect(commit(h, 3)).toBe(h);
    h = undo(h);
    expect(h.present).toBe(2);
    h = redo(h);
    expect(h.present).toBe(3);
    h = undo(undo(h));
    expect(h.present).toBe(1);
    expect(undo(h)).toBe(h);
    h = commit(h, 9);
    expect(h.future).toEqual([]);
    expect(redo(h)).toBe(h);
  });

  it("caps the stack", () => {
    let h = createHistory(0);
    for (let i = 1; i <= 150; i += 1) h = commit(h, i);
    expect(h.past).toHaveLength(100);
  });
});
