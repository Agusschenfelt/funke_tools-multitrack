import { describe, expect, it } from "vitest";
import { minimapSeekTarget } from "./minimapKeys";

// Bars every 2 s from 0.5 s; 20 s song.
const downbeats = [0.5, 2.5, 4.5, 6.5, 8.5, 10.5, 12.5, 14.5, 16.5, 18.5];
const at = (key: string, now: number, bars = downbeats) =>
  minimapSeekTarget(key, { now, downbeats: bars, duration: 20 });

describe("minimapSeekTarget", () => {
  it("ArrowRight goes to the next bar line", () => {
    expect(at("ArrowRight", 3)).toBe(4.5);
    expect(at("ArrowRight", 2.5)).toBe(4.5);
  });
  it("ArrowRight before the first bar goes to the first bar", () => {
    expect(at("ArrowRight", 0)).toBe(0.5);
  });
  it("ArrowRight after the last bar goes to the end", () => {
    expect(at("ArrowRight", 19)).toBe(20);
  });
  it("ArrowLeft returns to the start of the current bar when well into it", () => {
    expect(at("ArrowLeft", 5.9)).toBe(4.5);
  });
  it("ArrowLeft near a bar line goes to the previous bar", () => {
    expect(at("ArrowLeft", 4.6)).toBe(2.5);
    expect(at("ArrowLeft", 4.5)).toBe(2.5);
  });
  it("ArrowLeft at or before the first bar goes to zero", () => {
    expect(at("ArrowLeft", 0.5)).toBe(0);
    expect(at("ArrowLeft", 0.2)).toBe(0);
  });
  it("PageDown moves four bars forward", () => {
    expect(at("PageDown", 3)).toBe(10.5);
    expect(at("PageDown", 15)).toBe(20);
  });
  it("PageUp moves four bars back from a bar line, clamped at zero", () => {
    expect(at("PageUp", 12.5)).toBe(4.5);
    expect(at("PageUp", 3)).toBe(0);
  });
  it("PageUp from inside a bar lands four bar lines back counting the current one", () => {
    expect(at("PageUp", 13.9)).toBe(6.5);
  });
  it("Home and End jump to the ends", () => {
    expect(at("Home", 9)).toBe(0);
    expect(at("End", 9)).toBe(20);
  });
  it("falls back to seconds without a bar grid", () => {
    expect(at("ArrowRight", 10, [])).toBe(15);
    expect(at("ArrowLeft", 10, [])).toBe(5);
    expect(at("PageDown", 10, [])).toBe(20);
    expect(at("PageUp", 10, [])).toBe(0);
    expect(at("ArrowLeft", 2, [])).toBe(0);
  });
  it("ignores other keys", () => {
    expect(at("a", 3)).toBeNull();
    expect(at("ArrowUp", 3)).toBeNull();
  });
});
