import { describe, expect, it } from "vitest";
import { editControlsVisible, editMessage, type EditState } from "./toolbar";

const idle: EditState = {
  dirty: false,
  saving: false,
  canUndo: false,
  canRedo: false,
  editorOpen: false,
  status: { phase: "idle" },
};

describe("editControlsVisible", () => {
  it("is hidden when there is nothing to edit, save or report", () => {
    expect(editControlsVisible(idle)).toBe(false);
  });

  it.each<[string, Partial<EditState>]>([
    ["unsaved changes", { dirty: true }],
    ["a save in flight", { saving: true }],
    ["something to undo", { canUndo: true }],
    ["something to redo", { canRedo: true }],
    ["the section editor open", { editorOpen: true }],
    ["a saved notice", { status: { phase: "saved" } }],
    ["a save error", { status: { phase: "error", message: "x" } }],
  ])("shows for %s", (_, patch) => {
    expect(editControlsVisible({ ...idle, ...patch })).toBe(true);
  });
});

describe("editMessage", () => {
  it("is short while saving and after saving, and silent when idle", () => {
    expect(editMessage({ phase: "idle" })).toBe("");
    expect(editMessage({ phase: "saving" })).toBe("Guardando…");
    expect(editMessage({ phase: "saved" })).toBe("Guardado.");
  });

  it("keeps the full error with the reassurance that edits are still there", () => {
    const text = editMessage({ phase: "error", message: "Sin conexión." });
    expect(text).toContain("Sin conexión.");
    expect(text).toContain("Tus cambios siguen acá");
  });
});
