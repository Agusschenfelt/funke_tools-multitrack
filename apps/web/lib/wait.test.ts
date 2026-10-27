import { describe, expect, it } from "vitest";
import type { RowView } from "@/lib/processing";
import {
  chordsSummary,
  notifyState,
  rulerPosition,
  sectionRuns,
  separationEstimate,
  shouldNotify,
  stageLine,
  stepView,
  titleProgress,
} from "@/lib/wait";

const row = (over: Partial<RowView>): RowView => ({
  kind: "analyze",
  status: "running",
  stage: "decoding",
  seconds: 0,
  ...over,
});

describe("stepView", () => {
  it("counts the running stage among the job's steps", () => {
    expect(stepView(row({ stage: "decoding" }))).toEqual({ step: 1, total: 4, done: 0 });
    expect(stepView(row({ stage: "sections" }))).toEqual({ step: 3, total: 4, done: 2 });
    expect(stepView(row({ kind: "separate", stage: "previews" }))).toEqual({ step: 3, total: 4, done: 2 });
  });
  it("is complete when finished and not started when queued or unknown", () => {
    expect(stepView(row({ status: "finished", stage: "done" }))).toEqual({ step: 4, total: 4, done: 4 });
    expect(stepView(row({ status: "queued", stage: null })).done).toBe(0);
    expect(stepView(row({ stage: "mystery" })).step).toBe(0);
  });
});

describe("stageLine", () => {
  it("reads as a sentence per job and stage", () => {
    expect(stageLine(row({ stage: "analyzing" }))).toBe("Analizando · tempo y tonalidad");
    expect(stageLine(row({ kind: "separate", stage: "separating" }))).toBe("Separando pistas");
    expect(stageLine(row({ kind: "separate", stage: "previews" }))).toBe("Preparando las vistas previas");
  });
  it("covers waiting, finished and unknown stages", () => {
    expect(stageLine(row({ status: "queued", stage: null }))).toBe("En cola · esperando su turno");
    expect(stageLine(row({ status: "finished" }))).toBe("Análisis listo");
    expect(stageLine(row({ kind: "separate", status: "finished" }))).toBe("Pistas listas");
    expect(stageLine(row({ stage: "mystery" }))).toBe("Trabajando…");
  });
});

describe("rulerPosition", () => {
  it("starts at bar 1 and moves only as stages complete", () => {
    const start = [row({ stage: "decoding" }), row({ kind: "separate", status: "queued", stage: null })];
    expect(rulerPosition(start)).toEqual({ current: 1, passed: 0, finished: false });
    const mid = [
      row({ status: "finished", stage: "done" }),
      row({ kind: "separate", stage: "separating" }),
    ];
    expect(rulerPosition(mid)).toEqual({ current: 8, passed: 7, finished: false });
  });
  it("puts every bar behind the mark when both jobs are done", () => {
    const done = [
      row({ status: "finished", stage: "done" }),
      row({ kind: "separate", status: "finished", stage: "done" }),
    ];
    expect(rulerPosition(done)).toEqual({ current: 12, passed: 12, finished: true });
  });
});

describe("separationEstimate", () => {
  it("is 1.5 s per audio second, rounded to minutes, and labelled as an estimate", () => {
    expect(separationEstimate(240)).toBe("Suele tardar unos 6 minutos para un tema de 4. Es una estimación.");
  });
  it("handles short songs and singular minutes", () => {
    expect(separationEstimate(30)).toBe("Suele tardar cerca de 1 minuto para un tema de 1. Es una estimación.");
  });
  it("says nothing without a usable duration", () => {
    expect(separationEstimate(null)).toBe("");
    expect(separationEstimate(0)).toBe("");
    expect(separationEstimate(Number.NaN)).toBe("");
  });
});

describe("sectionRuns", () => {
  it("collapses consecutive repeats", () => {
    const runs = sectionRuns([{ name: "intro" }, { name: "chorus" }, { name: "chorus" }, { name: "verse" }]);
    expect(runs).toEqual([
      { label: "INTRO", count: 1 },
      { label: "CORO", count: 2 },
      { label: "ESTROFA", count: 1 },
    ]);
  });
});

describe("chordsSummary", () => {
  it("returns the four chords that sound longest", () => {
    const chords = [
      { start: 0, end: 10, label: "A" },
      { start: 10, end: 14, label: "E" },
      { start: 14, end: 30, label: "A" },
      { start: 30, end: 33, label: "F#m" },
      { start: 33, end: 40, label: "D" },
      { start: 40, end: 41, label: "B" },
    ];
    expect(chordsSummary(chords)).toEqual(["A", "D", "E", "F#m"]);
  });
  it("is empty without chords", () => {
    expect(chordsSummary(null)).toEqual([]);
    expect(chordsSummary(undefined)).toEqual([]);
    expect(chordsSummary([])).toEqual([]);
  });
});

describe("titleProgress", () => {
  const sep = (status: RowView["status"]) => row({ kind: "separate", status });
  it("names the job in progress", () => {
    expect(titleProgress([row({}), sep("queued")])).toBe("Analizando… · Multitrack");
    expect(titleProgress([row({ status: "finished" }), sep("running")])).toBe("Separando… · Multitrack");
  });
  it("shows done and problems", () => {
    expect(titleProgress([row({ status: "finished" }), sep("finished")])).toBe("✓ Listo · Multitrack");
    expect(titleProgress([row({ status: "finished" }), sep("failed")])).toBe("Hubo un problema · Multitrack");
  });
});

describe("notifications", () => {
  it("maps permission to states", () => {
    expect(notifyState("default")).toBe("default");
    expect(notifyState("granted")).toBe("granted");
    expect(notifyState("denied")).toBe("denied");
    expect(notifyState(undefined)).toBe("unsupported");
  });
  it("fires only when granted and the tab is hidden", () => {
    expect(shouldNotify("granted", true)).toBe(true);
    expect(shouldNotify("granted", false)).toBe(false);
    expect(shouldNotify("default", true)).toBe(false);
  });
});
