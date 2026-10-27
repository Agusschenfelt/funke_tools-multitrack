import { describe, expect, it } from "vitest";
import { dragHasFiles, isOverlayVisible, nextDragDepth, type DragStep } from "./fileDrag";

const run = (steps: DragStep[]) => steps.reduce(nextDragDepth, 0);

describe("dragHasFiles", () => {
  it("accepts a drag that includes Files", () => {
    expect(dragHasFiles(["text/plain", "Files"])).toBe(true);
  });
  it("ignores text and link drags", () => {
    expect(dragHasFiles(["text/plain", "text/uri-list"])).toBe(false);
  });
  it("ignores a missing or empty type list", () => {
    expect(dragHasFiles(null)).toBe(false);
    expect(dragHasFiles(undefined)).toBe(false);
    expect(dragHasFiles([])).toBe(false);
  });
});

describe("nextDragDepth", () => {
  it("stays visible while the pointer crosses nested elements", () => {
    // enter window, enter child, leave parent (flicker), leave child entered earlier
    const depth = run(["enter", "enter", "leave"]);
    expect(depth).toBe(1);
    expect(isOverlayVisible(depth)).toBe(true);
  });
  it("hides once every entered element was left", () => {
    expect(isOverlayVisible(run(["enter", "enter", "leave", "leave"]))).toBe(false);
  });
  it("never goes negative on a stray leave", () => {
    expect(run(["leave", "leave"])).toBe(0);
    expect(run(["leave", "enter"])).toBe(1);
  });
  it("reset (drop or Escape) hides it from any depth", () => {
    expect(run(["enter", "enter", "enter", "reset"])).toBe(0);
  });
});
