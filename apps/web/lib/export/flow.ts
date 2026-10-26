/** Wording and decisions around exporting, kept pure so they can be tested. */
import { ApiError } from "@/lib/api";

export type StartProblem = "missing" | "other";

/** 409 means the analysis or the stems are not there yet: the way out is the processing screen. */
export function startProblem(error: unknown): StartProblem {
  return error instanceof ApiError && error.kind === "http" && error.status === 409 ? "missing" : "other";
}

/** Plain-Spanish reason for a failed stagepack job; the raw server text stays out of the UI. */
export function packFailureMessage(error: string | null): string {
  const text = (error ?? "").toLowerCase();
  if (/timeout|timed out|expired/.test(text)) return "Armar el pack tardó demasiado y se cortó. Probá de nuevo.";
  if (/memory|\boom\b|killed/.test(text)) return "El servidor se quedó sin memoria armando el pack. Probá de nuevo.";
  if (/beat grid|downbeat|count-in/.test(text)) {
    return "El análisis no tiene una grilla de tiempo usable para esta canción, así que no se puede armar el pack.";
  }
  return "No se pudo armar el pack. Probá de nuevo.";
}

/** Whether the studio's Exportar link may navigate: unsaved or saving section edits block it. */
export function exportBlockedBy(state: { dirty: boolean; saving: boolean }): "dirty" | "saving" | null {
  if (state.saving) return "saving";
  return state.dirty ? "dirty" : null;
}
