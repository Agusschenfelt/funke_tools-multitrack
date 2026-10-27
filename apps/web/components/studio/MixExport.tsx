"use client";

import { useEffect, useRef, useState } from "react";
import { MixExportError, type StudioEngine } from "@/lib/audio/engine";
import { wavSize, mixFilename, type BitDepth } from "@/lib/audio/mixdown";
import type { StemSource } from "@/lib/audio/stems";
import { formatBytes } from "@/lib/format";
import { MIX_DOWNLOAD_LABEL } from "@/lib/studio/downloads";
import styles from "./MixExport.module.css";

interface MixExportProps {
  id: string;
  engine: StudioEngine;
  title: string;
  /** Seconds; sizes the estimate. */
  duration: number;
  /** The studio holds compressed previews. */
  compressed: boolean;
  /** WAV stems for a full-quality render; empty when the song has none. */
  wavSources: readonly StemSource[];
  /** Click and cues exist (the song has a grid). */
  hasGrid: boolean;
  /** Every stem is muted: nothing would be heard. */
  silent: boolean;
  ready: boolean;
}

type Phase = "download" | "mix" | "encode";
type Run =
  | { status: "idle" }
  | { status: "working"; phase: Phase; fraction: number }
  | { status: "done"; name: string; bytes: number; reducedDb: number }
  | { status: "error"; message: string };

const PHASE_TEXT: Record<Phase, string> = {
  download: "Descargando las pistas sin comprimir",
  mix: "Mezclando",
  encode: "Armando el WAV",
};

function errorText(error: unknown): string {
  if (error instanceof MixExportError) {
    switch (error.kind) {
      case "download":
        return "No pudimos descargar las pistas sin comprimir. Revisá tu conexión o probá con la calidad del estudio.";
      case "decode":
        return "Este navegador no pudo leer las pistas sin comprimir.";
      case "cues":
        return "No se pudieron cargar las guías habladas. Probá sin guías.";
      case "notReady":
        return "Esperá a que terminen de cargar las pistas.";
      default:
        return "No se pudo mezclar en este navegador. Probá con 16 bits o con menos opciones.";
    }
  }
  return "No se pudo generar la mezcla.";
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  // The browser has taken the file by then; keep the URL alive a moment for slow starts.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Renders what the lanes sound like now into a WAV, in the browser, with progress. Lives in the downloads panel. */
export function MixExport({
  id,
  engine,
  title,
  duration,
  compressed,
  wavSources,
  hasGrid,
  silent,
  ready,
}: MixExportProps) {
  const [bitDepth, setBitDepth] = useState<BitDepth>(16);
  const [withClick, setWithClick] = useState(false);
  const [full, setFull] = useState(false);
  const [run, setRun] = useState<Run>({ status: "idle" });
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const canFull = compressed && wavSources.length > 0;
  const useFull = canFull && full;
  const frames = Math.round(duration * 44100);
  // 16-bit stereo is the smallest a stem can be; the real download may be larger.
  const downloadEstimate = wavSources.length * wavSize(frames, 16);
  const working = run.status === "working";

  const start = async () => {
    const controller = new AbortController();
    abort.current = controller;
    setRun({ status: "working", phase: useFull ? "download" : "mix", fraction: 0 });
    try {
      const result = await engine.exportMix({
        bitDepth,
        includeClick: withClick,
        includeCues: withClick,
        fullQuality: useFull ? wavSources : undefined,
        signal: controller.signal,
        onProgress: ({ phase, fraction }) => setRun({ status: "working", phase, fraction }),
      });
      if (controller.signal.aborted) return;
      const name = mixFilename(title);
      saveBlob(result.blob, name);
      setRun({ status: "done", name, bytes: result.blob.size, reducedDb: result.reducedDb });
    } catch (error) {
      if (controller.signal.aborted) {
        setRun({ status: "idle" });
        return;
      }
      setRun({ status: "error", message: errorText(error) });
    } finally {
      abort.current = null;
    }
  };

  return (
    <div id={id} className={styles.panel} role="group" aria-label={MIX_DOWNLOAD_LABEL}>
      <p className={styles.lead}>
        Descarga la mezcla tal como la escuchás ahora: volúmenes, silencios, solos y paneos. El loop no
        cuenta, sale la canción entera.
      </p>

      <div className={styles.options}>
        <fieldset className={styles.field} disabled={working}>
          <legend className={styles.legend}>Formato</legend>
          <label className={styles.choice}>
            <input type="radio" name={`${id}-bits`} checked={bitDepth === 16} onChange={() => setBitDepth(16)} />
            WAV 16 bits
          </label>
          <label className={styles.choice}>
            <input type="radio" name={`${id}-bits`} checked={bitDepth === 24} onChange={() => setBitDepth(24)} />
            WAV 24 bits
          </label>
        </fieldset>

        <fieldset className={styles.field} disabled={working}>
          <legend className={styles.legend}>Acompañamiento</legend>
          <label className={styles.choice}>
            <input
              type="checkbox"
              checked={withClick && hasGrid}
              disabled={!hasGrid}
              onChange={(event) => setWithClick(event.target.checked)}
            />
            Incluir click y guías habladas
          </label>
        </fieldset>

        {canFull && (
          <fieldset className={styles.field} disabled={working}>
            <legend className={styles.legend}>Calidad</legend>
            <label className={styles.choice}>
              <input type="radio" name={`${id}-quality`} checked={!full} onChange={() => setFull(false)} />
              La del estudio (vista previa comprimida)
            </label>
            <label className={styles.choice}>
              <input type="radio" name={`${id}-quality`} checked={full} onChange={() => setFull(true)} />
              Completa (baja las pistas WAV)
            </label>
          </fieldset>
        )}
      </div>

      <p className={styles.note}>
        {compressed
          ? useFull
            ? `Va a descargar de nuevo las pistas sin comprimir: al menos ${formatBytes(downloadEstimate)} y más tiempo de espera. `
            : "El estudio tiene cargada la vista previa comprimida: este WAV sale con esa calidad. "
          : "Se usan las pistas sin comprimir que están cargadas. "}
        Se genera en tu navegador y pesa unos {formatBytes(wavSize(frames, bitDepth))}.
      </p>

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.go}
          disabled={!ready || working || silent}
          onClick={() => void start()}
        >
          {working ? "Generando…" : "Generar WAV"}
        </button>
        {working && (
          <button type="button" className={styles.cancel} onClick={() => abort.current?.abort()}>
            Cancelar
          </button>
        )}
        {silent && <span className={styles.note}>Todas las pistas están silenciadas.</span>}
      </div>

      <div role="status" aria-live="polite" className={styles.status}>
        {run.status === "working" && (
          <>
            <progress className={styles.progress} max={1} value={run.fraction} aria-label={PHASE_TEXT[run.phase]} />
            <span className="mono">
              {PHASE_TEXT[run.phase]} · {Math.round(run.fraction * 100)} %
            </span>
          </>
        )}
        {run.status === "done" && (
          <span>
            Listo: <span className="mono">{run.name}</span> ({formatBytes(run.bytes)}).
            {run.reducedDb > 0.05 &&
              ` Bajamos el nivel ${run.reducedDb.toLocaleString("es-AR", { maximumFractionDigits: 1 })} dB para que no sature.`}
          </span>
        )}
        {run.status === "error" && <span className={styles.error}>{run.message}</span>}
      </div>
    </div>
  );
}
