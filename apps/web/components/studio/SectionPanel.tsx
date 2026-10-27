"use client";

import { useState, type ReactNode } from "react";
import type { Section, SectionName } from "@/lib/api";
import { barAt, SECTION_OPTIONS } from "@/lib/sections/edit";
import { sectionLabel } from "@/lib/processing";
import { editMessage } from "@/lib/studio/toolbar";
import type { SaveStatus } from "./useSectionEditor";
import styles from "./SectionPanel.module.css";

interface EditControlsProps {
  /** In the toolbar row: buttons match the row's 36px height instead of the editor's 44px. */
  dense?: boolean;
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
  /** Undo, redo and save: they live in the editor row while it is open, since it covers the toolbar. */
  edit?: ReactNode;
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
 * Undo, redo and save for the section edits, at the end of the toolbar row. The caller renders
 * it only while there is something to edit (see `editControlsVisible`); the keyboard shortcuts
 * work either way.
 */
export function EditControls({
  dense = false,
  dirty,
  saving,
  status,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onSave,
}: EditControlsProps) {
  const message = editMessage(status);
  return (
    <div className={dense ? `${styles.edit} ${styles.dense}` : styles.edit} role="group" aria-label="Editar secciones">
      <button
        type="button"
        className={styles.button}
        disabled={!canUndo}
        aria-keyshortcuts="Control+Z Meta+Z"
        onClick={onUndo}
      >
        Deshacer
      </button>
      <button
        type="button"
        className={styles.button}
        disabled={!canRedo}
        aria-keyshortcuts="Control+Shift+Z Meta+Shift+Z"
        onClick={onRedo}
      >
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
      </p>
    </div>
  );
}

/**
 * The selected section's name, label and structure actions. On desktop it is a single-row bar
 * overlaying a thin band under the strip; on a phone it is a bottom sheet above the transport.
 * Either way selecting a section never moves the waveforms. Escape closes it.
 */
export function SectionEditor({
  edit = null,
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
          <button type="button" className={`${styles.button} ${styles.close}`} onClick={onClose}>
            Cerrar
          </button>
        </div>
        <div className={styles.fields}>
          <label className={styles.field}>
            <span className={styles.fieldName}>Nombre</span>
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
            <span className={styles.fieldName}>Etiqueta propia (opcional)</span>
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
            aria-label="Inicio de la sección, un compás antes"
            disabled={!hasGrid || selected === 0}
            onClick={() => onNudge(selected, -1)}
          >
            −1 compás
          </button>
          <button
            type="button"
            className={styles.button}
            aria-label="Inicio de la sección, un compás después"
            disabled={!hasGrid || selected === 0}
            onClick={() => onNudge(selected, 1)}
          >
            +1 compás
          </button>
          <button
            type="button"
            className={styles.button}
            aria-label="Dividir en el cursor"
            disabled={!hasGrid}
            onClick={onSplit}
          >
            Dividir
          </button>
          <button
            type="button"
            className={styles.button}
            aria-label="Unir con la anterior"
            disabled={selected === 0}
            onClick={() => onMerge(selected, "prev")}
          >
            Unir ←
          </button>
          <button
            type="button"
            className={styles.button}
            aria-label="Unir con la siguiente"
            disabled={selected >= sections.length - 1}
            onClick={() => onMerge(selected, "next")}
          >
            Unir →
          </button>
        </div>
        {edit}
        {!hasGrid && (
          <p className={styles.hint}>
            Sin grilla de compases no se pueden mover los bordes ni dividir; sí renombrar y unir.
          </p>
        )}
      </div>
    </section>
  );
}
