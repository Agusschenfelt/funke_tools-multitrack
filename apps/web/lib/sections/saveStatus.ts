export type SaveStatus =
  | { phase: "idle" }
  | { phase: "saving" }
  | { phase: "saved" }
  | { phase: "error"; message: string };

/**
 * Status after the sections change (an edit, undo or redo). A stale "saved" or error would no
 * longer describe what is on screen, so it resets; a save in flight is left alone.
 */
export function statusAfterEdit(status: SaveStatus): SaveStatus {
  return status.phase === "saving" ? status : { phase: "idle" };
}
