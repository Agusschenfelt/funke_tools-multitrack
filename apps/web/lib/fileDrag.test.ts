import { describe, expect, it } from "vitest";
import {
  dragHasFiles,
  isOverlayVisible,
  nextDragDepth,
  reduceWindowDrag,
  type DragStep,
  type WindowDragInput,
} from "./fileDrag";

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

describe("reduceWindowDrag", () => {
  const FILES = ["Files"];
  const TEXT = ["text/plain"];
  const file = { name: "a.wav" } as File;
  const enter: WindowDragInput = { kind: "enter", types: FILES };

  it("shows the overlay on a file drag entering and hides it after leaving", () => {
    const shown = reduceWindowDrag(0, true, enter);
    expect(shown).toMatchObject({ depth: 1, visible: true, preventDefault: false, file: null });
    expect(reduceWindowDrag(1, true, { kind: "leave", types: FILES })).toMatchObject({
      depth: 0,
      visible: false,
    });
  });

  it("ignores drags that carry no files", () => {
    for (const kind of ["enter", "leave", "over"] as const) {
      expect(reduceWindowDrag(2, true, { kind, types: TEXT })).toEqual({
        depth: 2,
        visible: true,
        preventDefault: false,
        file: null,
      });
    }
    const drop = reduceWindowDrag(0, true, { kind: "drop", types: TEXT, file });
    expect(drop).toMatchObject({ preventDefault: false, file: null });
  });

  it("cancels dragover of a file so the drop can fire", () => {
    expect(reduceWindowDrag(1, true, { kind: "over", types: FILES })).toMatchObject({
      depth: 1,
      preventDefault: true,
    });
  });

  it("a drop hides the overlay, is cancelled and hands over the file", () => {
    expect(reduceWindowDrag(3, true, { kind: "drop", types: FILES, file })).toEqual({
      depth: 0,
      visible: false,
      preventDefault: true,
      file,
    });
  });

  it("a drop without a file yields none", () => {
    expect(reduceWindowDrag(1, true, { kind: "drop", types: FILES, file: null }).file).toBeNull();
  });

  it("Escape hides the overlay from any depth", () => {
    expect(reduceWindowDrag(4, true, { kind: "escape" })).toMatchObject({ depth: 0, visible: false });
  });

  it("while disabled: no overlay, no file, but file drags are still cancelled", () => {
    expect(reduceWindowDrag(0, false, enter)).toMatchObject({ depth: 0, visible: false });
    expect(reduceWindowDrag(0, false, { kind: "over", types: FILES }).preventDefault).toBe(true);
    expect(reduceWindowDrag(0, false, { kind: "drop", types: FILES, file })).toMatchObject({
      preventDefault: true,
      file: null,
    });
  });
});
