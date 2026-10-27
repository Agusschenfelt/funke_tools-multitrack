/**
 * Pure logic for the processing view: polling cadence, stage and status wording, elapsed time,
 * failure messages and the songbook line of detected sections. No React, no fetch.
 */
import type { JobKind, JobOut, JobStatus, Section } from "@/lib/api";

/* -------------------------------------------------------------- polling */

export const POLL_FIRST_MS = 1500;
export const POLL_MAX_MS = 5000;
const POLL_GROWTH = 1.4;

/** Delay before the next poll: 1.5 s, growing 1.4x per consecutive poll, capped at 5 s. */
export function nextPollDelay(attempt: number): number {
  const n = Math.max(0, Math.floor(attempt));
  return Math.min(POLL_MAX_MS, Math.round(POLL_FIRST_MS * POLL_GROWTH ** n));
}

export function isTerminal(status: JobStatus): boolean {
  return status === "finished" || status === "failed";
}

/* -------------------------------------------------------------- wording */

const STAGES: Record<string, string> = {
  decoding: "Leyendo audio",
  analyzing: "Tempo y tonalidad",
  sections: "Secciones",
  separating: "Separando pistas",
  loading: "Cargando pistas",
  packing: "Armando el pack",
  saving: "Guardando",
  done: "Listo",
};

/** Spanish stage name; an unknown stage is shown as a dash rather than raw English. */
export function stageLabel(stage: string | null): string {
  return stage ? (STAGES[stage] ?? "—") : "—";
}

const STATUSES: Record<JobStatus, string> = {
  queued: "En cola",
  running: "En curso",
  finished: "Listo",
  failed: "Falló",
};

export function statusLabel(status: JobStatus): string {
  return STATUSES[status];
}

export const TASK_LABEL: Record<Exclude<JobKind, "stagepack">, string> = {
  analyze: "Análisis",
  separate: "Separación",
};

/** Plain-Spanish reason for a failed job; the raw server text stays out of the UI. */
export function failureMessage(kind: Exclude<JobKind, "stagepack">, error: string | null): string {
  // The worker's own Spanish message for an over-long song is already user-facing: show it as is.
  const tooLong = (error ?? "").match(/El tema dura \d+:\d{2} y el máximo es \d+:\d{2}\./);
  if (tooLong) return tooLong[0];
  const text = (error ?? "").toLowerCase();
  if (/out of memory|\boom\b|memory|killed/.test(text)) {
    return "El servidor se quedó sin memoria con este archivo. Probá con un archivo más corto.";
  }
  if (/decod|ffmpeg|codec|format|invalid data|could not read/.test(text)) {
    return "No pudimos leer el audio de este archivo. Probá con otro formato.";
  }
  if (/timeout|timed out|expired/.test(text)) {
    return "El proceso tardó demasiado y se cortó.";
  }
  return kind === "analyze" ? "El análisis falló." : "La separación falló.";
}

/* ----------------------------------------------------------------- time */

/** Seconds a job has taken (finished) or has been going (queued or running); null if unknown. */
export function elapsedSeconds(job: JobOut, nowMs: number): number | null {
  const start = Date.parse(job.started_at ?? job.created_at);
  if (Number.isNaN(start)) return null;
  const end = job.finished_at ? Date.parse(job.finished_at) : nowMs;
  if (Number.isNaN(end)) return null;
  return Math.max(0, (end - start) / 1000);
}

/** `m:ss`, or `h:mm:ss` from one hour. */
export function formatElapsed(seconds: number | null): string {
  if (seconds === null) return "–:––";
  const total = Math.floor(seconds);
  const s = total % 60;
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** `m:ss` for a song duration. */
export function formatDuration(seconds: number): string {
  return formatElapsed(seconds);
}

/* ------------------------------------------------------------- sections */

const SECTION_NAMES: Record<string, string> = {
  intro: "INTRO",
  verse: "ESTROFA",
  verse_2: "ESTROFA 2",
  pre_chorus: "PRECORO",
  chorus: "CORO",
  bridge: "PUENTE",
  solo: "SOLO",
  instrumental: "INSTRUMENTAL",
  break: "BREAK",
  outro: "FINAL",
  tag: "TAG",
};

export function sectionLabel(section: Pick<Section, "name" | "label">): string {
  const custom = section.label?.trim();
  if (custom) return custom.toLocaleUpperCase("es-AR");
  return SECTION_NAMES[section.name] ?? section.name.toLocaleUpperCase("es-AR");
}

/** Songbook line: `INTRO · ESTROFA · CORO ×2 · PUENTE`. Consecutive identical labels collapse. */
export function sectionsSummary(sections: readonly Pick<Section, "name" | "label">[]): string {
  const runs: { label: string; count: number }[] = [];
  for (const section of sections) {
    const label = sectionLabel(section);
    const last = runs[runs.length - 1];
    if (last && last.label === label) last.count += 1;
    else runs.push({ label, count: 1 });
  }
  return runs.map(({ label, count }) => (count > 1 ? `${label} ×${count}` : label)).join(" · ");
}

export function keyModeLabel(mode: string): string {
  const m = mode.toLowerCase();
  if (m === "major") return "mayor";
  if (m === "minor") return "menor";
  return mode;
}

/* --------------------------------------------------------- job tracking */

export interface TrackedJobs {
  analyze: string | null;
  separate: string | null;
}

/** Job ids from the URL query (`?a=&s=`), falling back to what this tab stored for the song. */
export function resolveTracked(
  query: { a?: string | string[]; s?: string | string[] },
  stored: TrackedJobs | null,
): TrackedJobs {
  const one = (value: string | string[] | undefined) =>
    (Array.isArray(value) ? value[0] : value) || null;
  return {
    analyze: one(query.a) ?? stored?.analyze ?? null,
    separate: one(query.s) ?? stored?.separate ?? null,
  };
}

export type RowKind = Exclude<JobKind, "stagepack">;

export interface RowView {
  kind: RowKind;
  /** "checking": a job id is tracked but its first poll has not answered yet. */
  status: JobStatus | "untracked" | "checking";
  stage: string | null;
  seconds: number | null;
}

/**
 * One table row. A finished artifact wins over a missing or expired job; with neither a job nor
 * an artifact there is nothing to follow ("untracked"), unless a tracked job has not been polled
 * yet ("checking"), which must not read as missing data.
 */
export function rowView(
  kind: RowKind,
  job: JobOut | null,
  artifactReady: boolean,
  nowMs: number,
  awaitingPoll = false,
): RowView {
  if (job) {
    return {
      kind,
      status: job.status,
      stage: job.stage,
      seconds: elapsedSeconds(job, nowMs),
    };
  }
  if (artifactReady) return { kind, status: "finished", stage: "done", seconds: null };
  if (awaitingPoll) return { kind, status: "checking", stage: null, seconds: null };
  return { kind, status: "untracked", stage: null, seconds: null };
}
