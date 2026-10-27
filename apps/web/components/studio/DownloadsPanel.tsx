"use client";

import type { StudioEngine } from "@/lib/audio/engine";
import type { StemSource } from "@/lib/audio/stems";
import { DOWNLOADS_LABEL, MIX_DOWNLOAD_LABEL, stemDownloads } from "@/lib/studio/downloads";
import { MixExport } from "./MixExport";
import styles from "./DownloadsPanel.module.css";

interface DownloadsPanelProps {
  id: string;
  engine: StudioEngine;
  title: string;
  duration: number;
  compressed: boolean;
  wavSources: readonly StemSource[];
  hasGrid: boolean;
  silent: boolean;
  ready: boolean;
  /** Quiet line about what the studio loaded versus what gets exported. */
  note: string | null;
}

/**
 * Everything the browser can hand over as a file: each stem as a WAV, and the mix as it sounds
 * now. The Stage Pack is a different thing and has its own button in the song bar.
 */
export function DownloadsPanel({ id, wavSources, note, title, ...mix }: DownloadsPanelProps) {
  const stems = stemDownloads(wavSources, title);
  return (
    <section id={id} className={styles.panel} aria-label={DOWNLOADS_LABEL}>
      {stems.length > 0 && (
        <div className={styles.group}>
          <h2 className={styles.heading}>Cada pista (WAV sin comprimir)</h2>
          <ul className={styles.stems}>
            {stems.map((stem) => (
              <li key={stem.id}>
                <a className={styles.link} href={stem.url} download={stem.filename}>
                  <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
                    <path
                      d="M12 4v11m0 0l-4.5-4.5M12 15l4.5-4.5M5 19h14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="square"
                    />
                  </svg>
                  {stem.label}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className={styles.group}>
        <h2 className={styles.heading}>{MIX_DOWNLOAD_LABEL}</h2>
        <MixExport id={`${id}-mix`} title={title} wavSources={wavSources} {...mix} />
      </div>
      {note && <p className={styles.note}>{note}</p>}
    </section>
  );
}
