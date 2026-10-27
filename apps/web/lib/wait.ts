/**
 * Pure logic for the designed wait: stage lines and step counts per job, the typical-duration
 * hint, the ruler position, chord and section summaries, the tab title and the notification
 * state. No React, no fetch.
 */
import { PRODUCT_NAME } from "@/lib/brand";
import type { Analysis } from "@/lib/api";
import { sectionLabel, type RowKind, type RowView } from "@/lib/processing";

/* ----------------------------------------------------------- stage steps */

/** Worker stages in order, per job (workers/cpu/worker_cpu/jobs.py); "done" is not a step. */
const STEPS: Record<RowKind, readonly string[]> = {
  analyze: ["decoding", "analyzing", "sections", "saving"],
  separate: ["decoding", "separating", "previews", "saving"],
};

const LINES: Record<RowKind, Record<string, string>> = {
  analyze: {
    decoding: "Leyendo el audio",
    analyzing: "Analizando · tempo y tonalidad",
    sections: "Buscando las secciones",
    saving: "Guardando el análisis",
  },
  separate: {
    decoding: "Leyendo el audio",
    separating: "Separando pistas",
    previews: "Preparando las vistas previas",
    saving: "Guardando las pistas",
  },
};

export interface StepView {
  /** 1-based step now running; the total when finished; 0 while nothing has started. */
  step: number;
  total: number;
  /** Completed steps, 0..total. */
  done: number;
}

/** Stage k of n for a row. A queued or unknown stage counts as not started. */
export function stepView(row: Pick<RowView, "kind" | "status" | "stage">): StepView {
  const steps = STEPS[row.kind];
  const total = steps.length;
  if (row.status === "finished") return { step: total, total, done: total };
  if (row.status !== "running") return { step: 0, total, done: 0 };
  const index = row.stage ? steps.indexOf(row.stage) : -1;
  if (index < 0) return { step: 0, total, done: 0 };
  return { step: index + 1, total, done: index };
}

/** The readable line for a row: what the worker is doing now, or why nothing is yet. */
export function stageLine(row: Pick<RowView, "kind" | "status" | "stage">): string {
  const name = row.kind === "analyze" ? "Análisis" : "Separación";
  switch (row.status) {
    case "untracked":
      return `${name}: sin seguimiento`;
    case "checking":
      return "Consultando…";
    case "queued":
      return "En cola · esperando su turno";
    case "failed":
      return `${name}: falló`;
    case "finished":
      return row.kind === "analyze" ? "Análisis listo" : "Pistas listas";
    default:
      return (row.stage && LINES[row.kind][row.stage]) || "Trabajando…";
  }
}

/* ------------------------------------------------------------ ruler/bars */

export const RULER_BARS = 12;

/**
 * Position of the orange mark on the 12-bar ruler, 1-based, from the steps both jobs have
 * completed. Honest: it moves only when a stage changes. `finished` puts every bar behind it.
 */
export function rulerPosition(rows: readonly RowView[]): { current: number; passed: number; finished: boolean } {
  const views = rows.map(stepView);
  const total = views.reduce((sum, v) => sum + v.total, 0);
  const done = views.reduce((sum, v) => sum + v.done, 0);
  if (total > 0 && done >= total) return { current: RULER_BARS, passed: RULER_BARS, finished: true };
  const passed = total > 0 ? Math.floor((done / total) * RULER_BARS) : 0;
  return { current: Math.min(RULER_BARS, passed + 1), passed, finished: false };
}

/* ------------------------------------------------------------- estimates */

/** Server-side separation costs about this many seconds per second of audio. */
export const SEPARATION_SECONDS_PER_AUDIO_SECOND = 1.5;

function minutesWord(n: number): string {
  return n === 1 ? "1 minuto" : `${n} minutos`;
}

/** "Suele tardar unos 6 minutos para un tema de 4 minutos. Es una estimación." Empty without a duration. */
export function separationEstimate(durationSeconds: number | null | undefined): string {
  if (typeof durationSeconds !== "number" || !Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    return "";
  }
  const wait = Math.max(1, Math.round((durationSeconds * SEPARATION_SECONDS_PER_AUDIO_SECOND) / 60));
  const song = Math.max(1, Math.round(durationSeconds / 60));
  const how = wait === 1 ? "cerca de" : "unos";
  return `Suele tardar ${how} ${minutesWord(wait)} para un tema de ${minutesWord(song)}. Es una estimación.`;
}

/* ---------------------------------------------------------------- result */

export interface SectionRun {
  label: string;
  count: number;
}

/** Sections as songbook chips: consecutive identical labels collapse into one with a repeat count. */
export function sectionRuns(sections: readonly Parameters<typeof sectionLabel>[0][]): SectionRun[] {
  const runs: SectionRun[] = [];
  for (const section of sections) {
    const label = sectionLabel(section);
    const last = runs[runs.length - 1];
    if (last && last.label === label) last.count += 1;
    else runs.push({ label, count: 1 });
  }
  return runs;
}

/** The chords that sound longest, most present first. Ties keep first-appearance order. */
export function chordsSummary(chords: Analysis["chords"], limit = 4): string[] {
  if (!chords || chords.length === 0) return [];
  const totals = new Map<string, number>();
  for (const chord of chords) {
    const length = chord.end - chord.start;
    if (!(length > 0) || !chord.label) continue;
    totals.set(chord.label, (totals.get(chord.label) ?? 0) + length);
  }
  return [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([label]) => label);
}

/* -------------------------------------------------------------- tab title */

type Phase = RowView["status"];

/** Tab title for the wait: what is going on, then the product name. */
export function titleProgress(rows: readonly Pick<RowView, "kind" | "status">[]): string {
  const by = (kind: RowKind): Phase | undefined => rows.find((r) => r.kind === kind)?.status;
  const analyze = by("analyze");
  const separate = by("separate");
  let text: string;
  if (analyze === "failed" || separate === "failed") text = "Hubo un problema";
  else if (rows.length > 0 && rows.every((r) => r.status === "finished")) text = "✓ Listo";
  else if (analyze !== "finished" && analyze !== undefined && analyze !== "untracked") text = "Analizando…";
  else if (separate === "queued" || separate === "running" || separate === "checking") text = "Separando…";
  else text = "Procesando…";
  return `${text} · ${PRODUCT_NAME}`;
}

/* ---------------------------------------------------------- notification */

export type NotifyState = "unsupported" | "default" | "granted" | "denied";

/** Maps the Notification permission (or its absence) to the states the UI distinguishes. */
export function notifyState(permission: string | null | undefined): NotifyState {
  if (permission === "default" || permission === "granted" || permission === "denied") return permission;
  return "unsupported";
}

/** Whether to fire a browser notification: granted, and the person is not looking at the tab. */
export function shouldNotify(state: NotifyState, tabHidden: boolean): boolean {
  return state === "granted" && tabHidden;
}
