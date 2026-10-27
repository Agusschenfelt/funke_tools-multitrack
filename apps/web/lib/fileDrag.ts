/**
 * Pure logic behind the full-page drop overlay. `dragenter`/`dragleave` fire for every element the
 * pointer crosses, so a depth counter (not a boolean) decides whether a file drag is still over
 * the window.
 */

/** True when the drag carries files (not selected text or a link). */
export function dragHasFiles(types: Iterable<string> | null | undefined): boolean {
  if (!types) return false;
  return Array.from(types).includes("Files");
}

export type DragStep = "enter" | "leave" | "reset";

/** Next nesting depth after a drag event; never negative. */
export function nextDragDepth(depth: number, step: DragStep): number {
  if (step === "reset") return 0;
  if (step === "enter") return depth + 1;
  return Math.max(0, depth - 1);
}

export function isOverlayVisible(depth: number): boolean {
  return depth > 0;
}

/** What the window listeners saw, reduced to what the overlay logic needs. */
export type WindowDragInput =
  | { kind: "enter" | "leave" | "over"; types: Iterable<string> | null | undefined }
  | { kind: "drop"; types: Iterable<string> | null | undefined; file: File | null }
  | { kind: "escape" };

export interface WindowDragResult {
  depth: number;
  visible: boolean;
  /** The listener must call `event.preventDefault()` (keeps the browser from opening the file). */
  preventDefault: boolean;
  /** Hand this file to the consumer. */
  file: File | null;
}

/**
 * Event-to-state logic of `useWindowFileDrag`, kept pure so it can be tested without a DOM.
 * Drags without files are ignored. While disabled, a file drag is still cancelled on over/drop (so
 * the browser does not leave the page) but never shows the overlay or yields a file.
 */
export function reduceWindowDrag(
  depth: number,
  enabled: boolean,
  input: WindowDragInput,
): WindowDragResult {
  const idle = (next: number, preventDefault = false): WindowDragResult => ({
    depth: next,
    visible: isOverlayVisible(next),
    preventDefault,
    file: null,
  });
  if (input.kind === "escape") return idle(nextDragDepth(depth, "reset"));
  if (!dragHasFiles(input.types)) return idle(depth);
  switch (input.kind) {
    case "enter":
      return idle(enabled ? nextDragDepth(depth, "enter") : depth);
    case "leave":
      return idle(enabled ? nextDragDepth(depth, "leave") : depth);
    case "over":
      return idle(depth, true);
    case "drop":
      return { ...idle(nextDragDepth(depth, "reset"), true), file: enabled ? input.file : null };
  }
}
