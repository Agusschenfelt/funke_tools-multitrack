"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  describeError,
  getAnalysis,
  getSections,
  getSong,
  startAnalyze,
  startSeparate,
  type Analysis,
  type Section,
  type SongDetail,
} from "@/lib/api";
import {
  TASK_LABEL,
  failureMessage,
  formatDuration,
  isTerminal,
  keyModeLabel,
  resolveTracked,
  rowView,
  sectionsSummary,
  stageLabel,
  statusLabel,
  type RowKind,
  type RowView,
  type TrackedJobs,
} from "@/lib/processing";
import { createRetryGate, withJob } from "@/lib/retryGate";
import { readTracked, writeTracked } from "@/lib/trackedJobs";
import { JobTable } from "./JobTable";
import { useJob } from "./useJob";
import styles from "./ProcessingView.module.css";

type Query = { a?: string | string[]; s?: string | string[] };

type Load =
  | { phase: "loading" }
  | { phase: "ready"; song: SongDetail; tracked: TrackedJobs }
  | { phase: "missing" }
  | { phase: "error"; message: string };

export function ProcessingView({ songId, query }: { songId: string; query: Query }) {
  const [load, setLoad] = useState<Load>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);
  const { a, s } = query;

  useEffect(() => {
    const controller = new AbortController();
    getSong(songId, { signal: controller.signal })
      .then((song) => {
        const tracked = resolveTracked({ a, s }, readTracked(songId));
        setLoad({ phase: "ready", song, tracked });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.kind === "http" && error.status === 404) {
          setLoad({ phase: "missing" });
        } else {
          setLoad({ phase: "error", message: describeError(error) });
        }
      });
    return () => controller.abort();
  }, [songId, a, s, attempt]);

  return (
    <main className={styles.page}>
      {load.phase === "loading" && (
        <p className={styles.note} role="status">
          Cargando…
        </p>
      )}
      {load.phase === "missing" && (
        <div role="alert" className={styles.fatal}>
          <p>No encontramos esta canción. Los archivos se borran a las 24 h.</p>
          <Link href="/" className={styles.secondary}>
            Subir de nuevo
          </Link>
        </div>
      )}
      {load.phase === "error" && (
        <div role="alert" className={styles.fatal}>
          <p>{load.message}</p>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              setLoad({ phase: "loading" });
              setAttempt((n) => n + 1);
            }}
          >
            Reintentar
          </button>
        </div>
      )}
      {load.phase === "ready" && (
        <ProcessingBody songId={songId} initialSong={load.song} initialTracked={load.tracked} />
      )}
    </main>
  );
}

interface PartialData {
  analysis: Analysis;
  sections: Section[];
}

function ProcessingBody({
  songId,
  initialSong,
  initialTracked,
}: {
  songId: string;
  initialSong: SongDetail;
  initialTracked: TrackedJobs;
}) {
  const [song, setSong] = useState(initialSong);
  const [tracked, setTracked] = useState(initialTracked);
  const [now, setNow] = useState(() => Date.now());
  const [partial, setPartial] = useState<PartialData | null>(null);
  const [retrying, setRetrying] = useState<readonly RowKind[]>([]);
  const [retryError, setRetryError] = useState<string | null>(null);

  const analyzePoll = useJob(tracked.analyze);
  const separatePoll = useJob(tracked.separate);

  // Latest ids for retries that finish out of order; the gate drops results from superseded retries.
  const trackedRef = useRef(initialTracked);
  const [gate] = useState(createRetryGate);

  // A tracked job with no answer yet (and not reported lost) is loading, not missing.
  const analyzeRow = rowView("analyze", analyzePoll.job, song.artifacts.analysis, now,
    Boolean(tracked.analyze) && !analyzePoll.lost);
  const separateRow = rowView(
    "separate",
    separatePoll.job,
    song.artifacts.stems.length > 0,
    now,
    Boolean(tracked.separate) && !separatePoll.lost,
  );
  const rows = [analyzeRow, separateRow];
  const live = rows.some((row) => row.status === "queued" || row.status === "running");
  const analysisDone = analyzeRow.status === "finished";
  const allDone = rows.every((row) => row.status === "finished");
  const offline = analyzePoll.offline || separatePoll.offline;

  // One-second clock for the Tiempo column, only while something is moving.
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [live]);

  // A job reaching a terminal state changes which artifacts exist: refresh the song.
  const analyzeTerminal = analyzePoll.job ? isTerminal(analyzePoll.job.status) : false;
  const separateTerminal = separatePoll.job ? isTerminal(separatePoll.job.status) : false;
  useEffect(() => {
    if (!analyzeTerminal && !separateTerminal) return;
    const controller = new AbortController();
    getSong(songId, { signal: controller.signal })
      .then(setSong)
      .catch(() => {
        // The table already reflects the job; the next refresh will retry.
      });
    return () => controller.abort();
  }, [songId, analyzeTerminal, separateTerminal]);

  // Partial result as soon as analysis exists.
  useEffect(() => {
    if (!analysisDone) return;
    const controller = new AbortController();
    const { signal } = controller;
    Promise.all([
      getAnalysis(songId, { signal }),
      getSections(songId, { signal }).catch(() => null),
    ])
      .then(([analysis, sections]) => setPartial({ analysis, sections: sections?.sections ?? [] }))
      .catch(() => {
        // Not available yet or removed: the table still tells the story.
      });
    return () => controller.abort();
  }, [songId, analysisDone]);

  const restart = useCallback(
    async (kind: RowKind) => {
      const ticket = gate.begin(kind);
      setRetrying((list) => (list.includes(kind) ? list : [...list, kind]));
      setRetryError(null);
      try {
        const created =
          kind === "analyze"
            ? await startAnalyze(songId, { sections: true })
            : await startSeparate(songId);
        // A newer retry of this row won the race: its id stays.
        if (!gate.isCurrent(kind, ticket)) return;
        const next = withJob(trackedRef.current, kind, created.job_id);
        trackedRef.current = next;
        setTracked(next);
        writeTracked(songId, next);
        setNow(Date.now());
      } catch (error) {
        if (gate.isCurrent(kind, ticket)) setRetryError(describeError(error));
      } finally {
        if (gate.isCurrent(kind, ticket)) setRetrying((list) => list.filter((k) => k !== kind));
      }
    },
    [songId, gate],
  );

  const announcement = rows
    .map((row) => `${TASK_LABEL[row.kind]}: ${rowSpeech(row)}`)
    .join(". ");

  return (
    <>
      <h1 className={styles.title}>{song.filename}</h1>

      <section aria-labelledby="cola-titulo" className={styles.block}>
        <h2 id="cola-titulo" className={styles.heading}>
          Procesos
        </h2>
        <JobTable rows={rows} />
        <p className="visually-hidden" role="status" aria-live="polite">
          {announcement}
        </p>

        {offline && (
          <p className={styles.note}>Sin conexión con el servidor. Seguimos intentando.</p>
        )}
        {!allDone && separateRow.status !== "failed" && separateRow.status !== "untracked" && (
          <p className={styles.note}>
            La separación puede tardar varios minutos en este servidor. Dejá esta pestaña abierta;
            el análisis aparece en cuanto termina.
          </p>
        )}

        {rows.map((row) =>
          row.status === "failed" || row.status === "untracked" ? (
            <div key={row.kind} className={styles.problem} role="alert">
              <p>
                {row.status === "failed"
                  ? failureMessage(
                      row.kind,
                      (row.kind === "analyze" ? analyzePoll.job : separatePoll.job)?.error ?? null,
                    )
                  : `No encontramos el seguimiento de ${TASK_LABEL[row.kind].toLowerCase()}.`}
              </p>
              <button
                type="button"
                className={styles.secondary}
                disabled={retrying.includes(row.kind)}
                onClick={() => void restart(row.kind)}
              >
                {row.status === "failed" ? "Reintentar" : "Iniciar de nuevo"}
              </button>
            </div>
          ) : null,
        )}
        {retryError && (
          <p className={styles.errorText} role="alert">
            {retryError}
          </p>
        )}
      </section>

      {partial && <PartialResult partial={partial} />}

      {allDone && (
        <Link href={`/temas/${songId}/estudio`} className={styles.primary}>
          Abrir el estudio
        </Link>
      )}
    </>
  );
}

function rowSpeech(row: RowView): string {
  if (row.status === "untracked") return "sin seguimiento";
  if (row.status === "checking") return "consultando";
  if (row.status === "running") return `${statusLabel(row.status)}, ${stageLabel(row.stage)}`;
  return statusLabel(row.status);
}

function PartialResult({ partial }: { partial: PartialData }) {
  const { analysis, sections } = partial;
  const bpm = analysis.grid ? analysis.grid.bpm.toLocaleString("es-AR", { maximumFractionDigits: 1 }) : null;
  const summary = sectionsSummary(sections);
  return (
    <section aria-labelledby="parcial-titulo" className={styles.block}>
      <h2 id="parcial-titulo" className={styles.heading}>
        Resultado parcial
      </h2>
      <dl className={styles.facts}>
        {analysis.key && (
          <div className={styles.fact}>
            <dt>Tonalidad</dt>
            <dd>
              <span className={`${styles.big} mono`}>{analysis.key.key}</span>{" "}
              <span className={styles.mode}>{keyModeLabel(analysis.key.mode)}</span>
            </dd>
          </div>
        )}
        {bpm && (
          <div className={styles.fact}>
            <dt>Tempo</dt>
            <dd>
              <span className={`${styles.big} mono`}>{bpm}</span>{" "}
              <span className={styles.mode}>BPM</span>
            </dd>
          </div>
        )}
        {analysis.grid && (
          <div className={styles.fact}>
            <dt>Compás</dt>
            <dd className="mono">{analysis.grid.time_signature}</dd>
          </div>
        )}
        <div className={styles.fact}>
          <dt>Duración</dt>
          <dd className="mono">{formatDuration(analysis.duration)}</dd>
        </div>
      </dl>
      {summary && (
        <div className={styles.form}>
          <h3 className={styles.formLabel}>Secciones detectadas</h3>
          <p className={`${styles.formLine} mono`}>{summary}</p>
        </div>
      )}
    </section>
  );
}
