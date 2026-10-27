"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { CUSTOM_LABEL, PRESETS, type MixPreset, type PresetId } from "@/lib/audio/presets";
import { DOWNLOADS_LABEL } from "@/lib/studio/downloads";
import styles from "./MixBar.module.css";

interface MixBarProps {
  preset: MixPreset;
  disabled: boolean;
  onPreset: (id: PresetId) => void;
  /** What the active loop covers ("compases 5 a 8"); null when none. */
  loopLabel: string | null;
  /** The section under the playhead can be repeated. */
  canLoopSection: boolean;
  onLoopSection: () => void;
  onClearLoop: () => void;
  ruler: "bars" | "time";
  onRuler: (mode: "bars" | "time") => void;
  downloadsOpen: boolean;
  onToggleDownloads: () => void;
  /** Id of the downloads panel, for aria-controls. */
  downloadsId: string;
  /** Deshacer, Rehacer and Guardar: rendered at the end of the row only while they matter. */
  edit?: ReactNode;
}

/**
 * The studio's single toolbar row: quick mixes on the left, ruler, loop and downloads on the
 * right, and the section-edit controls only while there is something to edit. "Personalizado"
 * lights up by itself once mute/solo is changed by hand. On a phone the presets become a select
 * and the rest folds into "Más", which opens in the page flow so it never covers a lane.
 */
export function MixBar({
  preset,
  disabled,
  onPreset,
  loopLabel,
  canLoopSection,
  onLoopSection,
  onClearLoop,
  ruler,
  onRuler,
  downloadsOpen,
  onToggleDownloads,
  downloadsId,
  edit = null,
}: MixBarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const barRef = useRef<HTMLDivElement>(null);

  // Phone menu: Escape closes it. On wide screens the menu is always inline.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className={styles.bar} ref={barRef}>
      <div className={`${styles.group} ${styles.presets}`} role="group" aria-label="Mezclas rápidas">
        {PRESETS.map(({ id, label, hint }) => (
          <button
            key={id}
            type="button"
            className={styles.segment}
            aria-pressed={preset === id}
            title={hint}
            disabled={disabled}
            onClick={() => onPreset(id)}
          >
            {label}
          </button>
        ))}
        <span
          className={styles.segment}
          data-custom={preset === "custom" ? "active" : "idle"}
          title="Las pistas ya no coinciden con una mezcla rápida"
          aria-hidden={preset === "custom" ? undefined : "true"}
        >
          {CUSTOM_LABEL}
        </span>
      </div>
      <label className={styles.mix}>
        <span className={styles.mixLabel}>Mezcla</span>
        <select
          className={styles.select}
          value={preset}
          disabled={disabled}
          onChange={(event) => {
            const id = event.target.value;
            if (id !== "custom") onPreset(id as PresetId);
          }}
        >
          {PRESETS.map(({ id, label, hint }) => (
            <option key={id} value={id} title={hint}>
              {label}
            </option>
          ))}
          {preset === "custom" && <option value="custom">{CUSTOM_LABEL}</option>}
        </select>
      </label>
      <button
        type="button"
        className={`${styles.small} ${styles.more}`}
        aria-expanded={menuOpen}
        aria-controls={menuId}
        onClick={() => setMenuOpen((open) => !open)}
      >
        Más
      </button>
      <div id={menuId} className={styles.menu} data-open={menuOpen ? "true" : "false"}>
        <div className={styles.tools}>
          <div className={styles.group} role="group" aria-label="La regla marca">
            <button
              type="button"
              className={styles.segment}
              aria-pressed={ruler === "bars"}
              onClick={() => onRuler("bars")}
            >
              Compases
            </button>
            <button
              type="button"
              className={styles.segment}
              aria-pressed={ruler === "time"}
              onClick={() => onRuler("time")}
            >
              Tiempo
            </button>
          </div>
          {!loopLabel && (
            <button
              type="button"
              className={styles.small}
              title="También podés arrastrar sobre la regla para repetir un tramo"
              disabled={disabled || !canLoopSection}
              onClick={() => {
                setMenuOpen(false);
                onLoopSection();
              }}
            >
              Repetir esta sección
            </button>
          )}
          <button
            type="button"
            className={styles.small}
            aria-expanded={downloadsOpen}
            aria-controls={downloadsId}
            onClick={() => {
              setMenuOpen(false);
              onToggleDownloads();
            }}
          >
            {DOWNLOADS_LABEL}
          </button>
        </div>
      </div>
      {loopLabel && (
        <div className={styles.loop}>
          <p className={`${styles.loopState} mono`}>Loop: {loopLabel}</p>
          <button type="button" className={styles.small} aria-keyshortcuts="L" onClick={onClearLoop}>
            Quitar loop
          </button>
        </div>
      )}
      {edit}
    </div>
  );
}
