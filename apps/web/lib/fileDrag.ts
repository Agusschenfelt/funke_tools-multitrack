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
