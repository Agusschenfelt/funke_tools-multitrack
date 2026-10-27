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
  type SongDetail,
} from "@/lib/api";
import {
  TASK_LABEL,
  failureMessage,
  isTerminal,
  resolveTracked,
  rowView,
  stageLabel,
  statusLabel,
  type RowKind,
  type RowView,
  type TrackedJobs,
} from "@/lib/processing";
import { createRetryGate, withJob } from "@/lib/retryGate";
import { readTracked, writeTracked } from "@/lib/trackedJobs";
import { titleFromFilename } from "@/lib/strip";
import { rulerPosition, separationEstimate, stepView, titleProgress } from "@/lib/wait";
import { JobTable } from "./JobTable";
import { ResultFill, type PartialData } from "./ResultFill";
import { StageLines } from "./StageLines";
import { WaitRuler } from "./WaitRuler";
import { useCompletionNotice, useTabTitle } from "./useWaitSignals";
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
  const [wasWaiting, setWasWaiting] = useState(false);

  const analyzePoll = useJob(tracked.analyze);
  const separatePoll = useJob(tracked.separate);

  // Latest ids for retries that finish out of order; the gate drops results from superseded retries.
  const trackedRef = useRef(initialTracked);
  const [gate] = useState(createRetryGate);
  const openRef = useRef<HTMLAnchorElement>(null);

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
  const title = titleFromFilename(song.filename);

  // Only a wait the person watched earns the finale (focus and notice); a finished page just opens.
  useEffect(() => {
    // Remembering that the view saw work in flight is an effect of that work, not derived state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (live) setWasWaiting(true);
  }, [live]);

  useTabTitle(titleProgress(rows));
  const notice = useCompletionNotice(allDone, wasWaiting, title);

  // The finale: when the wait ends in front of the person, hand them the next action.
  useEffect(() => {
    if (allDone && wasWaiting) openRef.current?.focus();
  }, [allDone, wasWaiting]);

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
        // Not available yet or removed: the stage lines still tell the story.
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

  const announcement = allDone
    ? ""
    : rows.map((row) => `${TASK_LABEL[row.kind]}: ${rowSpeech(row)}`).join(". ");

  const ruler = rulerPosition(rows);
  const totals = rows.map(stepView);
  const stepsDone = totals.reduce((sum, v) => sum + v.done, 0);
  const stepsTotal = totals.reduce((sum, v) => sum + v.total, 0);
  const separating = separateRow.status === "queued" || separateRow.status === "running" ||
    separateRow.status === "checking";
  const estimate = separating ? separationEstimate(song.duration ?? partial?.analysis.duration) : "";
  const stuck = rows.some((row) => row.status === "failed" || row.status === "untracked");

  return (
    <>
      <h1 className={styles.title}>{title}</h1>

      <section aria-labelledby="cola-titulo" className={styles.block}>
        <h2 id="cola-titulo" className={styles.heading}>
          {allDone ? "Todo listo" : "Preparando la canción"}
        </h2>
        <WaitRuler
          current={ruler.current}
          passed={ruler.passed}
          finished={ruler.finished}
          active={live}
          valueNow={stepsDone}
          valueMax={stepsTotal}
        />
        <StageLines rows={rows} />
        <p className="visually-hidden" role="status" aria-live="polite">
          {announcement}
        </p>

        {offline && (
          <p className={styles.note}>Sin conexión con el servidor. Seguimos intentando.</p>
        )}
        {estimate && <p className={styles.note}>{estimate}</p>}

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

        {!stuck && (
          <div className={styles.slot}>
            <p className={styles.slotLine} role="status">
              {allDone
                ? "Análisis y pistas listos. Ya podés abrir el estudio."
                : analysisDone
                  ? "El análisis ya está. Las pistas llevan más; el estudio las necesita todas."
                  : "Dejá esta pestaña abierta: te avisamos acá cuando esté."}
            </p>
            <div className={styles.slotAction}>
              {allDone ? (
                <Link
                  ref={openRef}
                  href={`/temas/${songId}/estudio`}
                  className={`${styles.primary} ${wasWaiting ? styles.arrive : ""}`}
                >
                  Abrir el estudio
                </Link>
              ) : notice.state === "default" ? (
                <button type="button" className={styles.secondary} onClick={notice.request}>
                  Avisarme con una notificación
                </button>
              ) : notice.state === "granted" ? (
                <p className={styles.slotHint}>Te vamos a mandar una notificación al terminar.</p>
              ) : null}
            </div>
          </div>
        )}

        <details className={styles.detail}>
          <summary>Detalle</summary>
          <JobTable rows={rows} />
        </details>
      </section>

      <ResultFill partial={partial} complete={allDone} />
    </>
  );
}

function rowSpeech(row: RowView): string {
  if (row.status === "untracked") return "sin seguimiento";
  if (row.status === "checking") return "consultando";
  if (row.status === "running") return `${statusLabel(row.status)}, ${stageLabel(row.stage)}`;
  return statusLabel(row.status);
}
