import Link from "next/link";
import type { Analysis } from "@/lib/api";
import { keyModeLabel } from "@/lib/processing";
import styles from "./Studio.module.css";

/** Title, key and tempo in chord-sheet mono, and the way out to the export. */
export function SongBar({
  songId,
  title,
  analysis,
}: {
  songId: string;
  title: string;
  analysis: Analysis;
}) {
  const bpm = analysis.grid
    ? analysis.grid.bpm.toLocaleString("es-AR", { maximumFractionDigits: 1 })
    : null;
  return (
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
      <Link href={`/temas/${songId}/exportar`} className={styles.export}>
        Exportar
      </Link>
    </header>
  );
}
