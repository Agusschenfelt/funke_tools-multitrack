import Link from "next/link";
import { useState } from "react";
import type { Analysis } from "@/lib/api";
import { exportBlockedBy } from "@/lib/export/flow";
import { keyModeLabel } from "@/lib/processing";
import styles from "./Studio.module.css";

/** Title, key and tempo in chord-sheet mono, and the way out to the export. */
export function SongBar({
  songId,
  title,
  analysis,
  dirty,
  saving,
  onSave,
}: {
  songId: string;
  title: string;
  analysis: Analysis;
  /** Unsaved section edits: the export would not include them, so the link holds until saved. */
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
}) {
  const [tried, setTried] = useState(false);
  const blocked = exportBlockedBy({ dirty, saving });
  const bpm = analysis.grid
    ? analysis.grid.bpm.toLocaleString("es-AR", { maximumFractionDigits: 1 })
    : null;
  return (
    <>
      <header className={styles.songBar}>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.facts}>
          {analysis.key && (
            <span className={styles.fact}>
              <span className="mono">{analysis.key.key}</span>{" "}
              <span className={styles.mode}>{keyModeLabel(analysis.key.mode)}</span>
            </span>
          )}
          {bpm && (
            <span className={styles.fact}>
              <span className="mono">{bpm}</span> <span className={styles.mode}>BPM</span>
            </span>
          )}
          {analysis.grid && (
            <span className={`${styles.fact} ${styles.meter} mono`}>{analysis.grid.time_signature}</span>
          )}
        </p>
        <Link
          href={`/temas/${songId}/exportar`}
          className={styles.export}
          onClick={(event) => {
            if (!blocked) return;
            event.preventDefault();
            setTried(true);
          }}
        >
          Exportar
        </Link>
      </header>
      <div role="status" aria-live="polite">
        {tried && blocked && (
          <div className={styles.hold}>
            <p>
              {blocked === "saving"
                ? "Guardando las secciones… esperá a que termine para exportar."
                : "Tenés cambios sin guardar en las secciones. El pack usa las secciones guardadas: guardalas antes de exportar."}
            </p>
            {blocked === "dirty" && (
              <button type="button" className={styles.action} onClick={onSave}>
                Guardar ahora
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}
