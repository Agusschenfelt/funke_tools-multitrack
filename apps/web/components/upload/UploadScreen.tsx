"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { ApiError, describeError, startAnalyze, startSeparate, uploadSong } from "@/lib/api";
import type { TrackedJobs } from "@/lib/processing";
import { processingQuery, startMissingJobs } from "@/lib/startJobs";
import { formatBytes } from "@/lib/format";
import { ACCEPT, MAX_UPLOAD_MB, formatsLabel, validateFile } from "@/lib/upload";
import { BarProgress } from "./BarProgress";
import styles from "./UploadScreen.module.css";

type State =
  | { phase: "idle" }
  | { phase: "dragging" }
  | { phase: "uploading"; file: File; fraction: number }
  | { phase: "starting"; file: File }
  | { phase: "error"; message: string; songId?: string; file?: File; started?: TrackedJobs };

export function UploadScreen() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<State>({ phase: "idle" });

  useEffect(() => () => abortRef.current?.abort(), []);

  const startJobs = useCallback(
    async (songId: string, file: File, started: TrackedJobs = { analyze: null, separate: null }) => {
      setState({ phase: "starting", file });
      // Only the jobs that are not running yet are enqueued, so a retry never duplicates one.
      const { tracked, error } = await startMissingJobs(started, {
        analyze: () => startAnalyze(songId, { sections: true }),
        separate: () => startSeparate(songId),
      });
      if (error) {
        setState({ phase: "error", message: describeError(error), songId, file, started: tracked });
        return;
      }
      // The processing view follows these ids; it keeps them in the URL so a reload still works.
      router.push(`/temas/${songId}?${processingQuery(tracked)}`);
    },
    [router],
  );

  const upload = useCallback(
    async (file: File) => {
      const check = validateFile(file);
      if (!check.ok) {
        setState({ phase: "error", message: check.message });
        return;
      }
      const controller = new AbortController();
      abortRef.current = controller;
      setState({ phase: "uploading", file, fraction: 0 });
      try {
        const song = await uploadSong(file, {
          signal: controller.signal,
          onProgress: (fraction) => setState({ phase: "uploading", file, fraction }),
        });
        await startJobs(song.id, file);
      } catch (error) {
        if (error instanceof ApiError && error.kind === "aborted") {
          setState({ phase: "idle" });
          return;
        }
        setState({ phase: "error", message: describeError(error) });
      }
    },
    [startJobs],
  );

  const pick = () => inputRef.current?.click();

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) void upload(file);
    else setState({ phase: "idle" });
  };

  const busy = state.phase === "uploading" || state.phase === "starting";
  const file = "file" in state ? state.file : undefined;

  return (
    <main className={styles.page}>
      <h1 className={styles.title}>Subí una canción</h1>
      <p className={styles.lead}>
        Separamos las pistas y analizamos tempo, tonalidad y secciones. Después la escuchás y
        corregís lo que haga falta antes de exportar.
      </p>

      <div
        className={styles.zone}
        data-state={state.phase}
        onDragOver={(event) => {
          event.preventDefault();
          if (!busy) setState({ phase: "dragging" });
        }}
        onDragLeave={() => state.phase === "dragging" && setState({ phase: "idle" })}
        onDrop={busy ? (event) => event.preventDefault() : onDrop}
      >
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept={ACCEPT}
          tabIndex={-1}
          aria-hidden="true"
          onChange={(event) => {
            const chosen = event.target.files?.[0];
            event.target.value = "";
            if (chosen) void upload(chosen);
          }}
        />

        {busy && file ? (
          <div className={styles.progress}>
            <p className={styles.fileLine}>
              <span className={styles.fileName}>{file.name}</span>
              <span className={`${styles.fileSize} mono`}>{formatBytes(file.size)}</span>
            </p>
            <BarProgress
              fraction={state.phase === "uploading" ? state.fraction : 1}
              label="Progreso de la subida"
            />
            <div className={styles.progressFoot}>
              <p className={styles.status} role="status">
                {state.phase === "uploading"
                  ? `Subiendo… ${Math.round(state.fraction * 100)} %`
                  : "Preparando el análisis y la separación…"}
              </p>
              {state.phase === "uploading" && (
                <button
                  type="button"
                  className={styles.secondary}
                  onClick={() => abortRef.current?.abort()}
                >
                  Cancelar
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className={styles.idle}>
            <BarProgress fraction={null} />
            <p className={styles.drop}>
              {state.phase === "dragging" ? "Soltá el archivo" : "Arrastrá el archivo acá"}
            </p>
            <button type="button" className={styles.primary} onClick={pick}>
              Elegir archivo
            </button>
            <p className={styles.constraints}>
              {formatsLabel()}. Hasta {MAX_UPLOAD_MB} MB.
            </p>
          </div>
        )}
      </div>

      {state.phase === "error" && (
        <div className={styles.error} role="alert">
          <p>{state.message}</p>
          {state.songId && state.file ? (
            <button
              type="button"
              className={styles.secondary}
              onClick={() => void startJobs(state.songId!, state.file!, state.started)}
            >
              Reintentar
            </button>
          ) : (
            <button type="button" className={styles.secondary} onClick={pick}>
              Elegir otro archivo
            </button>
          )}
        </div>
      )}

      <p className={styles.rights}>
        La herramienta separa audio y no otorga derechos sobre la música que subís. Subí solo
        canciones que tengas derecho a usar. Los archivos se borran a las 24 h.
      </p>
    </main>
  );
}
