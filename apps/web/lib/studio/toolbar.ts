/** When the section-edit controls (Deshacer, Rehacer, Guardar) earn a place in the toolbar. */
import type { SaveStatus } from "@/lib/sections/saveStatus";

export interface EditState {
  dirty: boolean;
  saving: boolean;
  canUndo: boolean;
  canRedo: boolean;
  /** A section is chosen and its editor is open. */
  editorOpen: boolean;
  status: SaveStatus;
}

/**
 * Hidden until there is something to undo, save or report, or the editor is open. The shortcuts
 * (Cmd/Ctrl+Z, Shift+Cmd/Ctrl+Z) never depend on this: they are bound to the window.
 */
export function editControlsVisible(state: EditState): boolean {
  return (
    state.dirty ||
    state.saving ||
    state.canUndo ||
    state.canRedo ||
    state.editorOpen ||
    state.status.phase !== "idle"
  );
}

/**
 * The one-line status next to the edit controls. Short on purpose: the toolbar row is tight, and
 * an enabled Guardar already says there are unsaved changes. Errors keep their full text.
 */
export function editMessage(status: SaveStatus): string {
  switch (status.phase) {
    case "saving":
      return "Guardando…";
    case "saved":
      return "Guardado.";
    case "error":
      return `No se pudieron guardar las secciones. ${status.message} Tus cambios siguen acá.`;
    default:
      return "";
  }
}
