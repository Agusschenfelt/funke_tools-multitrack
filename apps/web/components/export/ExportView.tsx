"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  describeError,
  getAnalysis,
  getSong,
  startStagepack,
  type Analysis,
  type SongDetail,
} from "@/lib/api";
import { absoluteUrl, orderStems } from "@/lib/audio/stems";
import { packFailureMessage, startProblem } from "@/lib/export/flow";
import {
  readOptions,
  toApiBody,
  writeOptions,
  type ExportOptions,
} from "@/lib/export/options";
import { packFiles, zipName } from "@/lib/export/pack";
import { formatElapsed, elapsedSeconds, keyModeLabel, stageLabel } from "@/lib/processing";
import { titleFromFilename } from "@/lib/strip";
import { useJob } from "../processing/useJob";
import { OptionsForm } from "./OptionsForm";
import { PackPreview } from "./PackPreview";
import styles from "./ExportView.module.css";

type Load =
  | { phase: "loading" }
  | { phase: "ready"; song: SongDetail; analysis: Analysis }
  | { phase: "missing" }
  | { phase: "nostems" }
  | { phase: "error"; message: string };

export function ExportView({ songId }: { songId: string }) {
  const [load, setLoad] = useState<Load>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    getSong(songId, { signal })
      .then(async (song) => {
        if (song.artifacts.stems.length === 0 || !song.artifacts.analysis) {
          setLoad({ phase: "nostems" });
          return;
        }
        const analysis = await getAnalysis(songId, { signal });
        setLoad({ phase: "ready", song, analysis });
      })
      .catch((error) => {
        if (signal.aborted) return;
        if (error instanceof ApiError && error.kind === "http" && error.status === 404) {
          setLoad({ phase: "missing" });
        } else {
          setLoad({ phase: "error", message: describeError(error) });
        }
      });
    return () => controller.abort();
  }, [songId, attempt]);

  return (
    <main className={styles.page}>
      {load.phase === "loading" && (
        <p className={styles.note} role="status">
          Cargando…
        </p>
      )}
      {load.phase === "missing" && (
        <div role="alert" className={styles.problem}>
          <p>No encontramos esta canción. Los archivos se borran a las 24 h.</p>
          <Link href="/" className={styles.secondary}>
            Subir de nuevo
          </Link>
        </div>
      )}
      {load.phase === "nostems" && (
        <div role="alert" className={styles.problem}>
          <p>Todavía faltan el análisis o las pistas. Mirá cómo va el procesamiento.</p>
          <Link href={`/temas/${songId}`} className={styles.secondary}>
            Ver el procesamiento
          </Link>
        </div>
      )}
      {load.phase === "error" && (
        <div role="alert" className={styles.problem}>
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
      {load.phase === "ready" && <ExportBody songId={songId} song={load.song} analysis={load.analysis} />}
    </main>
  );
}

type Run =
  | { phase: "idle"; problem: { text: string; missing: boolean } | null }
  | { phase: "starting" }
  | { phase: "running"; jobId: string };

function ExportBody({
  songId,
  song,
  analysis,
}: {
  songId: string;
  song: SongDetail;
  analysis: Analysis;
}) {
  const [options, setOptions] = useState<ExportOptions>(() => readOptions());
  const [run, setRun] = useState<Run>({ phase: "idle", problem: null });
  const startAbort = useRef<AbortController | null>(null);
  useEffect(() => () => startAbort.current?.abort(), []);

  const { job, lost, offline } = useJob(run.phase === "running" ? run.jobId : null);

  const stems = useMemo(() => orderStems(song.artifacts.stems).map((s) => s.name), [song]);
  const files = useMemo(
    () => packFiles(options.destination, stems, options.includeVocals),
    [options.destination, stems, options.includeVocals],
  );
  const bpm = analysis.grid?.bpm ?? null;
  const zip = bpm !== null ? zipName(song.filename, analysis.key, bpm) : null;
  const canBuild = analysis.grid !== null;

  const change = (patch: Partial<ExportOptions>) => {
    setOptions((prev) => {
      const next = { ...prev, ...patch };
      writeOptions(next);
      return next;
    });
  };

  const launch = () => {
    if (!canBuild) return;
    const controller = new AbortController();
    startAbort.current = controller;
    setRun({ phase: "starting" });
    startStagepack(songId, toApiBody(options), { signal: controller.signal })
      .then(({ job_id }) => setRun({ phase: "running", jobId: job_id }))
      .catch((error) => {
        if (controller.signal.aborted) return;
        setRun({
          phase: "idle",
          problem: { text: describeError(error), missing: startProblem(error) === "missing" },
        });
      });
  };

  const now = useNow(run.phase !== "idle");
  const building = run.phase === "starting" || (run.phase === "running" && !isDone(job, lost));
  const finished = run.phase === "running" && job?.status === "finished" && job.download_url;
  const failed = run.phase === "running" && job?.status === "failed";
  const editedNote = song.artifacts.sections_edited
    ? "Usa las secciones que guardaste en el estudio."
    : "Usa las secciones detectadas automáticamente. Para corregirlas, editalas y guardalas en el estudio antes de exportar.";
  const detail = `WAV de 24 bits a ${options.sampleRate === 44100 ? "44,1" : "48"} kHz, todos con la misma duración y la cuenta previa de ${options.countInBars === 1 ? "1 compás" : "2 compases"} incluida.`;

  return (
    <>
      <h1 className={styles.title}>Exportar</h1>
      <p className={styles.song}>
        <span>{titleFromFilename(song.filename)}</span>
        {analysis.key && (
          <span className="mono">
            {" "}
            · {analysis.key.key} {keyModeLabel(analysis.key.mode)}
          </span>
        )}
        {bpm !== null && <span className="mono"> · {bpm.toLocaleString("es-AR", { maximumFractionDigits: 1 })} BPM</span>}
      </p>
      <p className={styles.note}>
        {editedNote} Los cambios sin guardar no entran en el pack.{" "}
        <Link href={`/temas/${songId}/estudio`}>Volver al estudio</Link>
      </p>

      {!canBuild && (
        <div role="alert" className={styles.problem}>
          <p>El análisis no encontró una grilla de tiempo, así que no se puede armar el pack de esta canción.</p>
        </div>
      )}

      <div className={styles.layout}>
        <OptionsForm options={options} disabled={building} onChange={change} />
        <div className={styles.side}>
          <PackPreview zip={zip ?? "Sin grilla de tiempo"} files={files} detail={detail} />

          <div className={styles.action}>
            {run.phase === "idle" && run.problem && (
              <div role="alert" className={styles.problem}>
                <p>{run.problem.text}</p>
                {run.problem.missing && (
                  <Link href={`/temas/${songId}`} className={styles.secondary}>
                    Ver el procesamiento
                  </Link>
                )}
              </div>
            )}

            <p className={styles.status} role="status" aria-live="polite">
              {run.phase === "starting" && "Enviando el pedido…"}
              {run.phase === "running" && !job && !lost && "Consultando el pack…"}
              {run.phase === "running" && job && !isTerminalStatus(job.status) && (
                <>
                  {job.status === "queued" ? "En cola" : stageLabel(job.stage) === "—" ? "En curso" : stageLabel(job.stage)}
                  {" · "}
                  <span className="mono">{formatElapsed(elapsedSeconds(job, now))}</span>
                  {offline && " · sin conexión, reintentando"}
                </>
              )}
              {finished && "El pack está listo."}
            </p>

            {failed && (
              <div role="alert" className={styles.problem}>
                <p>{packFailureMessage(job?.error ?? null)}</p>
              </div>
            )}
            {run.phase === "running" && lost && (
              <div role="alert" className={styles.problem}>
                <p>El servidor ya no recuerda este pedido. Armá el pack de nuevo.</p>
              </div>
            )}

            {finished && job?.download_url ? (
              <>
                <a className={styles.primary} href={absoluteUrl(job.download_url)} download>
                  Descargar ZIP
                </a>
                <p className={styles.hint}>
                  <span className="mono">{String(job.result?.filename ?? zip ?? "")}</span>. El enlace de
                  descarga vence: si ya no abre, armá el pack de nuevo.
                </p>
                <button type="button" className={styles.secondary} onClick={() => setRun({ phase: "idle", problem: null })}>
                  Armar otro pack con otras opciones
                </button>
              </>
            ) : failed || (run.phase === "running" && lost) ? (
              <button type="button" className={styles.primary} onClick={launch}>
                Reintentar
              </button>
            ) : (
              <button
                type="button"
                className={styles.primary}
                onClick={launch}
                disabled={building || !canBuild}
              >
                {building ? "Armando el pack…" : "Armar el pack"}
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function isTerminalStatus(status: string): boolean {
  return status === "finished" || status === "failed";
}

function isDone(job: { status: string } | null, lost: boolean): boolean {
  return lost || (job !== null && isTerminalStatus(job.status));
}

/** Wall clock that ticks once a second while `active`, so elapsed time can be derived during render. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(0);
  useEffect(() => {
    if (!active) return;
    // Resync on start: a stale value from a previous run would show the wrong elapsed time.
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [active]);
  return now;
}
