import { describe, expect, it } from "vitest";
import { barTicks, buildStrip, flatIndex, locateActive, stripItems, titleFromFilename } from "./strip";

const downbeats = Array.from({ length: 32 }, (_, i) => 0.5 + i * 2);
const sections = [
  { name: "intro" as const, label: null, start: 0.5 },
  { name: "verse" as const, label: null, start: 8.5 },
  { name: "chorus" as const, label: null, start: 16.5 },
  { name: "chorus" as const, label: null, start: 24.5 },
  { name: "bridge" as const, label: null, start: 32.5 },
];

describe("buildStrip", () => {
  const groups = buildStrip(sections, downbeats, 64.5);

  it("collapses consecutive identical labels into one repeat group", () => {
    expect(groups.map((g) => [g.label, g.count])).toEqual([
      ["INTRO", 1],
      ["ESTROFA", 1],
      ["CORO", 2],
      ["PUENTE", 1],
    ]);
    expect(groups[2]).toMatchObject({ start: 16.5, end: 32.5 });
    expect(groups[2].spans).toEqual([
      { start: 16.5, end: 24.5 },
      { start: 24.5, end: 32.5 },
    ]);
  });

  it("numbers the bar of each group start", () => {
    expect(groups.map((g) => g.startBar)).toEqual([1, 5, 9, 17]);
  });

  it("does not merge equal labels that are not adjacent", () => {
    const g = buildStrip(
      [sections[2], sections[1], { ...sections[2], start: 30 }],
      downbeats,
      64,
    );
    expect(g.map((x) => x.label)).toEqual(["CORO", "ESTROFA", "CORO"]);
  });

  it("uses custom labels and drops sections past the end", () => {
    const g = buildStrip([{ name: "verse", label: " estrofa a ", start: 0 }, { name: "tag", label: null, start: 99 }], downbeats, 60);
    expect(g.map((x) => x.label)).toEqual(["ESTROFA A"]);
  });

  it("has no start bar without a grid", () => {
    expect(buildStrip(sections, [], 64.5)[0].startBar).toBeNull();
  });

  it("locates the active group and repeat", () => {
    expect(locateActive(groups, 26)).toEqual({ group: 2, span: 1 });
    expect(locateActive(groups, 0.1)).toBeNull();
    expect(locateActive(groups, 64)).toEqual({ group: 3, span: 0 });
  });
});

describe("barTicks", () => {
  it("always includes anchors and spaces the rest", () => {
    const ticks = barTicks(downbeats, 64.5, 640, [1, 5, 9, 17], 36);
    expect(ticks.filter((t) => t.anchor).map((t) => t.bar)).toEqual([1, 5, 9, 17]);
    const xs = ticks.map((t) => (t.time / 64.5) * 640);
    for (let i = 1; i < xs.length; i += 1) expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual(35);
  });
  it("is empty without a grid or width", () => {
    expect(barTicks([], 60, 600, [])).toEqual([]);
    expect(barTicks(downbeats, 60, 0, [])).toEqual([]);
  });
});

describe("titleFromFilename", () => {
  it("drops the extension", () => {
    expect(titleFromFilename("mi_tema.final.mp3")).toBe("mi tema.final");
    expect(titleFromFilename("t.wav")).toBe("t");
  });
});

describe("stripItems and flatIndex", () => {
  it("flattens groups to one item per section with repeat ends", () => {
    const groups = buildStrip(sections, downbeats, 64);
    const items = stripItems(groups);
    expect(items.map((i) => i.index)).toEqual(items.map((_, n) => n));
    expect(items).toHaveLength(sections.length);
    const repeated = items.filter((i) => i.count > 1);
    expect(repeated.length).toBeGreaterThan(1);
    expect(repeated[0].first).toBe(true);
    expect(repeated[repeated.length - 1].last).toBe(true);
  });

  it("maps an active group and span to its flat index", () => {
    const groups = buildStrip(sections, downbeats, 64);
    const items = stripItems(groups);
    const g = groups.findIndex((x) => x.count > 1);
    expect(flatIndex(groups, { group: g, span: 1 })).toBe(items.findIndex((i) => i.group === g && !i.first));
    expect(flatIndex(groups, null)).toBeNull();
  });
});
