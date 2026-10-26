"use client";

import { useState } from "react";
import type { Section, SectionName } from "@/lib/api";
import { barAt, SECTION_OPTIONS } from "@/lib/sections/edit";
import { sectionLabel } from "@/lib/processing";
import type { SaveStatus } from "./useSectionEditor";
import styles from "./SectionPanel.module.css";

interface SectionPanelProps {
  sections: readonly Section[];
  selected: number | null;
  downbeats: readonly number[];
  dirty: boolean;
  saving: boolean;
  status: SaveStatus;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
  onRename: (index: number, name: SectionName, label: string | null) => void;
  onSplit: () => void;
  onMerge: (index: number, side: "prev" | "next") => void;
  onNudge: (index: number, bars: number) => void;
  onPlay: (index: number) => void;
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
 * Editing controls under the strip: undo/redo and save, then the selected section's name, label
 * and structure actions. On a phone it is a full-width panel with large controls; edges are moved
 * by the ±1 bar buttons instead of dragging.
 */
export function SectionPanel({
  sections,
  selected,
  downbeats,
  dirty,
  saving,
  status,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onSave,
  onRename,
  onSplit,
  onMerge,
  onNudge,
  onPlay,
}: SectionPanelProps) {
  const section = selected === null ? null : sections[selected];
  const hasGrid = downbeats.length > 0;
  const startBar = section ? barAt(downbeats, section.start) : null;
  const message = statusText(status);

  return (
    <section className={styles.panel} aria-label="Editar secciones">
      <div className={styles.bar}>
        <div className={styles.history}>
          <button type="button" className={styles.button} disabled={!canUndo} onClick={onUndo}>
            Deshacer
          </button>
          <button type="button" className={styles.button} disabled={!canRedo} onClick={onRedo}>
            Rehacer
          </button>
        </div>
        <p
          className={status.phase === "error" ? `${styles.message} ${styles.failed}` : styles.message}
          role={status.phase === "error" ? "alert" : "status"}
        >
          {message}
          {message === "" && dirty ? "Cambios sin guardar." : ""}
        </p>
        <button type="button" className={styles.save} disabled={!dirty || saving} onClick={onSave}>
          Guardar secciones
        </button>
      </div>

      {section && selected !== null ? (
        <div className={styles.editor}>
          <h2 className={styles.heading}>
            {sectionLabel(section)}
            {startBar !== null && <span className={`${styles.where} mono`}>desde el compás {startBar}</span>}
          </h2>
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
      ) : (
        <p className={styles.hint}>
          {sections.length === 0
            ? "Esta canción no tiene secciones."
            : "Elegí una sección para renombrarla, moverla o dividirla. Arrastrá el borde entre dos secciones para ajustarlo."}
        </p>
      )}
    </section>
  );
}
