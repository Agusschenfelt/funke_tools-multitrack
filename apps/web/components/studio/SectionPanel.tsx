"use client";

import { useState } from "react";
import type { Section, SectionName } from "@/lib/api";
import { barAt, SECTION_OPTIONS } from "@/lib/sections/edit";
import { sectionLabel } from "@/lib/processing";
import type { SaveStatus } from "./useSectionEditor";
import styles from "./SectionPanel.module.css";

interface SectionToolbarProps {
  sectionCount: number;
  dirty: boolean;
  saving: boolean;
  status: SaveStatus;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
}

interface SectionEditorProps {
  sections: readonly Section[];
  selected: number;
  downbeats: readonly number[];
  onRename: (index: number, name: SectionName, label: string | null) => void;
  onSplit: () => void;
  onMerge: (index: number, side: "prev" | "next") => void;
  onNudge: (index: number, bars: number) => void;
  onPlay: (index: number) => void;
  onClose: () => void;
}

function statusText(status: SaveStatus): string {
  switch (status.phase) {
    case "saving":
      return "Guardando las secciones…";
    case "saved":
      return "Secciones guardadas.";
    case "error":
      return `No se pudieron guardar las secciones. ${status.message} Tus cambios siguen acá.`;
    default:
      return "";
  }
}

/** The free label commits on Enter or blur, so history gets one step per label, not per key. */
function LabelField({ value, onCommit }: { value: string; onCommit: (label: string) => void }) {
  const [draft, setDraft] = useState(value);
  return (
    <input
      className={styles.input}
      type="text"
      value={draft}
      maxLength={40}
      placeholder="Ej.: Coro final"
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => onCommit(draft)}
      onKeyDown={(event) => {
        if (event.key === "Enter") onCommit(draft);
      }}
    />
  );
}

/**
 * History and save in one compact row above the strip, with the how-to text one tap away on a
 * phone so the strip and the first lane stay above the fold.
 */
export function SectionToolbar({
  sectionCount,
  dirty,
  saving,
  status,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onSave,
}: SectionToolbarProps) {
  const message = statusText(status);
  const hint =
    sectionCount === 0
      ? "Esta canción no tiene secciones."
      : "Elegí una sección para renombrarla, moverla o dividirla. Arrastrá el borde entre dos secciones para ajustarlo.";
  return (
    <section className={styles.panel} aria-label="Editar secciones">
      <div className={styles.bar}>
        <button type="button" className={styles.button} disabled={!canUndo} onClick={onUndo}>
          Deshacer
        </button>
        <button type="button" className={styles.button} disabled={!canRedo} onClick={onRedo}>
          Rehacer
        </button>
        <button type="button" className={styles.save} disabled={!dirty || saving} onClick={onSave}>
          Guardar
        </button>
        <p
          className={status.phase === "error" ? `${styles.message} ${styles.failed}` : styles.message}
          role={status.phase === "error" ? "alert" : "status"}
        >
          {message}
          {message === "" && dirty ? "Cambios sin guardar." : ""}
        </p>
      </div>
      <p className={styles.hintWide}>{hint}</p>
      <details className={styles.hintNarrow}>
        <summary>Cómo se editan</summary>
        <p className={styles.hint}>{hint}</p>
      </details>
    </section>
  );
}

/**
 * The selected section's name, label and structure actions. It opens as a sheet over the lanes
 * (anchored under the strip), so selecting a section never moves the waveforms. Escape closes it.
 */
export function SectionEditor({
  sections,
  selected,
  downbeats,
  onRename,
  onSplit,
  onMerge,
  onNudge,
  onPlay,
  onClose,
}: SectionEditorProps) {
  const section = sections[selected];
  const hasGrid = downbeats.length > 0;
  if (!section) return null;
  const startBar = barAt(downbeats, section.start);

  return (
    <section
      className={styles.sheet}
      aria-label="Sección elegida"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <div className={styles.editor}>
        <div className={styles.sheetHead}>
          <h2 className={styles.heading}>
            {sectionLabel(section)}
            {startBar !== null && <span className={`${styles.where} mono`}>desde el compás {startBar}</span>}
          </h2>
          <button type="button" className={styles.button} onClick={onClose}>
            Cerrar
          </button>
        </div>
        <div className={styles.fields}>
          <label className={styles.field}>
            <span>Nombre</span>
            <select
              className={styles.input}
              value={section.name}
              onChange={(event) =>
                onRename(selected, event.target.value as SectionName, section.label ?? null)
              }
            >
              {SECTION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.field}>
            <span>Etiqueta propia (opcional)</span>
            <LabelField
              key={`${selected}-${section.label ?? ""}`}
              value={section.label ?? ""}
              onCommit={(label) => onRename(selected, section.name, label)}
            />
          </label>
        </div>
        <div className={styles.actions}>
          <button type="button" className={styles.button} onClick={() => onPlay(selected)}>
            Escuchar
          </button>
          <button
            type="button"
            className={styles.button}
            disabled={!hasGrid || selected === 0}
            onClick={() => onNudge(selected, -1)}
          >
            Inicio −1 compás
          </button>
          <button
            type="button"
            className={styles.button}
            disabled={!hasGrid || selected === 0}
            onClick={() => onNudge(selected, 1)}
          >
            Inicio +1 compás
          </button>
          <button type="button" className={styles.button} disabled={!hasGrid} onClick={onSplit}>
            Dividir en el cursor
          </button>
          <button
            type="button"
            className={styles.button}
            disabled={selected === 0}
            onClick={() => onMerge(selected, "prev")}
          >
            Unir con la anterior
          </button>
          <button
            type="button"
            className={styles.button}
            disabled={selected >= sections.length - 1}
            onClick={() => onMerge(selected, "next")}
          >
            Unir con la siguiente
          </button>
        </div>
        {!hasGrid && (
          <p className={styles.hint}>
            Sin grilla de compases no se pueden mover los bordes ni dividir; sí renombrar y unir.
          </p>
        )}
      </div>
    </section>
  );
}
