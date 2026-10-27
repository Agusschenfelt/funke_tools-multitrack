import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import type { Analysis } from "@/lib/api";
import { exportBlockedBy } from "@/lib/export/flow";
import { keyLabel } from "@/lib/chords";
import { PACK_LABEL } from "@/lib/studio/downloads";
import { HELP_TITLE } from "@/lib/studio/help";
import { sanitizeTitle, UNTITLED, type TitleView } from "@/lib/studio/title";
import { HelpPanel } from "./HelpPanel";
import styles from "./Studio.module.css";

/**
 * The song's name. A generic file name ("Untitled") reads "Tema sin título" plus the duration;
 * clicking the name renames it for this browser only. Enter or leaving the field commits, Escape
 * cancels, an empty name goes back to the file's.
 */
function Title({ view, onRename }: { view: TitleView; onRename: (title: string | null) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const editing = draft !== null;

  useEffect(() => {
    if (editing) input.current?.select();
  }, [editing]);

  if (draft === null) {
    return (
      <h1 className={styles.title}>
        <button
          type="button"
          className={styles.titleButton}
          title="Renombrar (el nombre queda solo en este navegador)"
          onClick={() => setDraft(view.fallback ? "" : view.text)}
        >
          {view.text}
        </button>
        {view.detail && <span className={`${styles.duration} mono`}>{view.detail}</span>}
      </h1>
    );
  }
  const commit = () => {
    onRename(sanitizeTitle(draft));
    setDraft(null);
  };
  return (
    <h1 className={styles.title}>
      <input
        ref={input}
        className={styles.titleInput}
        type="text"
        value={draft}
        maxLength={80}
        placeholder={UNTITLED}
        aria-label="Nombre del tema (solo en este navegador)"
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
          if (event.key === "Escape") setDraft(null);
        }}
      />
    </h1>
  );
}

/** Title, key and tempo in chord-sheet mono, the help, and the way out to the Stage Pack export. */
export function SongBar({
  songId,
  title,
  analysis,
  dirty,
  saving,
  onSave,
  onRename,
  helpOpen,
  onToggleHelp,
}: {
  songId: string;
  title: TitleView;
  analysis: Analysis;
  /** Unsaved section edits: the export would not include them, so the link holds until saved. */
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  onRename: (title: string | null) => void;
  helpOpen: boolean;
  onToggleHelp: () => void;
}) {
  const [tried, setTried] = useState(false);
  const helpId = useId();
  const helpButton = useRef<HTMLButtonElement>(null);
  const blocked = exportBlockedBy({ dirty, saving });
  const bpm = analysis.grid
    ? analysis.grid.bpm.toLocaleString("es-AR", { maximumFractionDigits: 1 })
    : null;
  const key = analysis.key ? keyLabel(analysis.key) : null;
  return (
    <>
      <header className={styles.songBar}>
        <Title view={title} onRename={onRename} />
        <p className={styles.facts}>
          {key && (
            <span className={styles.fact} title={key.tooltip ?? undefined}>
              <span className="mono">{key.note}</span> <span className={styles.mode}>{key.mode}</span>
              {key.alternative && (
                <span className={styles.alternative}>
                  {" "}
                  (o {key.alternative})
                </span>
              )}
            </span>
          )}
          {bpm && (
            <span className={styles.fact}>
              <span className="mono">{bpm}</span> <span className={styles.mode}>BPM</span>
            </span>
          )}
          {analysis.grid && (
            <span className={`${styles.fact} ${styles.meter} mono`} title="Compás">
              {analysis.grid.time_signature}
            </span>
          )}
        </p>
        <button
          ref={helpButton}
          type="button"
          className={styles.help}
          aria-expanded={helpOpen}
          aria-controls={helpOpen ? helpId : undefined}
          aria-keyshortcuts="?"
          aria-label={HELP_TITLE}
          title={`${HELP_TITLE} (?)`}
          onClick={onToggleHelp}
        >
          ?
        </button>
        <Link
          href={`/temas/${songId}/exportar`}
          className={styles.export}
          title="Armar el Stage Pack: pistas, click y guías habladas para tu software de playback o DAW"
          onClick={(event) => {
            if (!blocked) return;
            event.preventDefault();
            setTried(true);
          }}
        >
          {PACK_LABEL}
        </Link>
        {helpOpen && <HelpPanel id={helpId} onClose={onToggleHelp} triggerRef={helpButton} />}
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
