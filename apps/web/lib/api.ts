/**
 * Typed client for the multitrack API.
 *
 * Types are hand-written from `apps/api/api/schemas.py` and `packages/audio-core/audio_core/models.py`
 * (dates travel as ISO strings). The base URL comes from NEXT_PUBLIC_API_URL.
 */
import { tooLargeMessage, unsupportedTypeMessage, emptyFileMessage } from "@/lib/upload";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

/* ---------------------------------------------------------------- types */

export type SectionName =
  | "intro"
  | "verse"
  | "verse_2"
  | "pre_chorus"
  | "chorus"
  | "bridge"
  | "solo"
  | "instrumental"
  | "break"
  | "outro"
  | "tag";

export interface Section {
  name: SectionName;
  /** Seconds in the original song, before the count-in pad. */
  start: number;
  label?: string | null;
  confidence?: number | null;
  cluster?: number | null;
}

export interface Sections {
  source?: string | null;
  sections: Section[];
}

export interface SectionsOut {
  source: string | null;
  sections: Section[];
  edited: boolean;
  updated_at: string | null;
}

export interface SongOut {
  id: string;
  filename: string;
  sha256: string;
  duration: number | null;
  created_at: string;
  expires_at: string;
}

export interface UploadOut extends SongOut {
  reused: boolean;
}

export interface ArtifactLink {
  name: string;
  url: string;
  token_expires_at: string;
}

export interface Analysis {
  source: string;
  duration: number;
  sample_rate: number;
  grid: { bpm: number; beats: number[]; downbeats: number[]; time_signature: string } | null;
  key: { key: string; mode: string; camelot: string } | null;
}

export interface Artifacts {
  analysis: boolean;
  sections: boolean;
  sections_edited: boolean;
  stems: ArtifactLink[];
  packs: ArtifactLink[];
}

export interface SongDetail extends SongOut {
  artifacts: Artifacts;
}

export type JobStatus = "queued" | "running" | "finished" | "failed";
export type JobKind = "analyze" | "separate" | "stagepack";

export interface JobOut {
  job_id: string;
  song_id: string;
  kind: JobKind;
  status: JobStatus;
  stage: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  download_url: string | null;
}

export interface JobCreated {
  job_id: string;
}

export type SeparationModel = "htdemucs_6s" | "htdemucs_ft";

export interface StagePackOptions {
  destination: "playback" | "daw";
  count_in_bars?: 1 | 2;
  click_sound?: "classic" | "cowbell" | "woodblock" | "rimshot";
  subdivision?: "quarter" | "eighth";
  straight_grid?: boolean;
  sample_rate?: 44100 | 48000;
  include_vocals?: boolean;
  language?: "es" | "en";
}

/* --------------------------------------------------------------- errors */

export type ApiErrorKind = "http" | "network" | "aborted" | "invalid";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  /** Raw `detail` from the API, kept for diagnostics; never shown to people. */
  readonly detail: string | null;

  constructor(kind: ApiErrorKind, status: number | null, detail: string | null = null) {
    super(messageForStatus(kind, status));
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

/** Human message (es-AR, voseo) for a failed request. */
export function messageForStatus(kind: ApiErrorKind, status: number | null): string {
  if (kind === "aborted") return "Se canceló la subida.";
  if (kind === "invalid") {
    return "El servidor devolvió datos que no podemos usar. Probá de nuevo o analizá la canción otra vez.";
  }
  if (kind === "network") {
    return "No hay conexión con el servidor. Revisá tu red y probá de nuevo.";
  }
  switch (status) {
    case 400:
      return emptyFileMessage();
    case 404:
      return "No encontramos esa canción. Los archivos se borran a las 24 h: subila de nuevo.";
    case 409:
      return "Todavía faltan el análisis o las pistas. Esperá a que terminen esos procesos.";
    case 413:
      return tooLargeMessage();
    case 415:
      return unsupportedTypeMessage();
    case 422:
      return "El servidor no aceptó los datos enviados. Revisalos y probá de nuevo.";
    case 503:
      return "El servidor no está disponible o está ocupado. Probá de nuevo en unos minutos.";
    default:
      return status !== null && status >= 500
        ? "El servidor tuvo un problema. Probá de nuevo en unos minutos."
        : "No pudimos completar la acción. Probá de nuevo.";
  }
}

/** Extracts FastAPI's `detail` (string or validation list) from a response body. */
export function parseDetail(body: string): string | null {
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : ""))
          .filter(Boolean)
          .join("; ");
      }
    }
  } catch {
    // Not JSON (proxy error page): no detail.
  }
  return null;
}

/** Message to show for anything thrown by this module or by the UI around it. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Algo salió mal. Probá de nuevo.";
}

/* ----------------------------------------------------------- validation */

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

function increasing(values: unknown): values is number[] {
  if (!Array.isArray(values)) return false;
  let previous = -Infinity;
  for (const value of values) {
    if (!finite(value) || value < 0 || value <= previous) return false;
    previous = value;
  }
  return true;
}

/**
 * True when a grid can drive the UI: positive BPM, beats and downbeats as finite, non-negative,
 * strictly increasing seconds, and a `n/d` time signature with positive integers.
 */
export function isValidGrid(grid: unknown): grid is NonNullable<Analysis["grid"]> {
  if (!grid || typeof grid !== "object") return false;
  const g = grid as Record<string, unknown>;
  if (!finite(g.bpm) || g.bpm <= 0) return false;
  if (!increasing(g.beats) || !increasing(g.downbeats)) return false;
  return typeof g.time_signature === "string" && /^[1-9]\d{0,2}\/[1-9]\d{0,2}$/.test(g.time_signature);
}

/** Boundary check for GET /analysis: a malformed grid becomes a clear error, never NaN in the UI. */
export function checkAnalysis(analysis: Analysis): Analysis {
  if (!analysis || typeof analysis !== "object" || !finite(analysis.duration)) {
    throw new ApiError("invalid", null, "analysis without a valid duration");
  }
  if (analysis.grid !== null && analysis.grid !== undefined && !isValidGrid(analysis.grid)) {
    throw new ApiError("invalid", null, "analysis grid has an invalid shape");
  }
  return analysis;
}

/* ------------------------------------------------------------- requests */

interface RequestOptions {
  signal?: AbortSignal;
}

async function request<T>(
  path: string,
  { method = "GET", body, signal }: RequestOptions & { method?: string; body?: unknown } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      signal,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("aborted", null);
    }
    throw new ApiError("network", null);
  }
  let text: string;
  try {
    text = await response.text();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("aborted", null);
    }
    // The body broke mid-read: an error status keeps its own message, a success is a lost response.
    if (!response.ok) throw new ApiError("http", response.status, errorDetail("", response));
    throw new ApiError("network", null);
  }
  if (!response.ok) {
    throw new ApiError("http", response.status, errorDetail(text, response));
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError("invalid", response.status, "response body is not JSON");
  }
}

/** The API's `detail` when the body has one; otherwise the HTTP status text (may be empty). */
function errorDetail(body: string, response: Pick<Response, "statusText">): string | null {
  return parseDetail(body) ?? (response.statusText || null);
}

export function getSong(songId: string, options: RequestOptions = {}): Promise<SongDetail> {
  return request<SongDetail>(`/songs/${encodeURIComponent(songId)}`, options);
}

export function startAnalyze(
  songId: string,
  body: { sections?: boolean } = { sections: true },
  options: RequestOptions = {},
): Promise<JobCreated> {
  return request<JobCreated>(`/songs/${encodeURIComponent(songId)}/analyze`, {
    ...options,
    method: "POST",
    body,
  });
}

export function startSeparate(
  songId: string,
  body: { model?: SeparationModel } = {},
  options: RequestOptions = {},
): Promise<JobCreated> {
  return request<JobCreated>(`/songs/${encodeURIComponent(songId)}/separate`, {
    ...options,
    method: "POST",
    body,
  });
}

export function getJob(jobId: string, options: RequestOptions = {}): Promise<JobOut> {
  return request<JobOut>(`/jobs/${encodeURIComponent(jobId)}`, options);
}

export async function getAnalysis(songId: string, options: RequestOptions = {}): Promise<Analysis> {
  const analysis = await request<Analysis>(`/songs/${encodeURIComponent(songId)}/analysis`, options);
  return checkAnalysis(analysis);
}

export function getSections(songId: string, options: RequestOptions = {}): Promise<SectionsOut> {
  return request<SectionsOut>(`/songs/${encodeURIComponent(songId)}/sections`, options);
}

export function putSections(
  songId: string,
  body: Sections,
  options: RequestOptions = {},
): Promise<SectionsOut> {
  return request<SectionsOut>(`/songs/${encodeURIComponent(songId)}/sections`, {
    ...options,
    method: "PUT",
    body,
  });
}

export function startStagepack(
  songId: string,
  options: StagePackOptions,
  requestOptions: RequestOptions = {},
): Promise<JobCreated> {
  return request<JobCreated>(`/songs/${encodeURIComponent(songId)}/stagepack`, {
    ...requestOptions,
    method: "POST",
    body: options,
  });
}

/** Multipart upload with progress (fetch has no upload progress, so this uses XMLHttpRequest). */
export function uploadSong(
  file: File,
  { onProgress, signal }: RequestOptions & { onProgress?: (fraction: number) => void } = {},
): Promise<UploadOut> {
  return new Promise<UploadOut>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError("aborted", null));
      return;
    }
    const xhr = new XMLHttpRequest();
    const onAbort = () => xhr.abort();
    signal?.addEventListener("abort", onAbort, { once: true });
    const done = () => signal?.removeEventListener("abort", onAbort);

    xhr.open("POST", `${API_URL}/songs`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () => {
      done();
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadOut);
        } catch {
          reject(new ApiError("http", xhr.status, "invalid JSON"));
        }
        return;
      }
      reject(new ApiError("http", xhr.status, parseDetail(xhr.responseText)));
    };
    xhr.onerror = () => {
      done();
      reject(new ApiError("network", null));
    };
    xhr.onabort = () => {
      done();
      reject(new ApiError("aborted", null));
    };

    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
