"use client";

import { useEffect, useId, useRef, useState } from "react";
import { CUSTOM_LABEL, PRESETS, type MixPreset, type PresetId } from "@/lib/audio/presets";
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
  exportOpen: boolean;
  onToggleExport: () => void;
  /** Id of the export panel, for aria-controls. */
  exportId: string;
  /** Download-size note; on a phone it lives in the "Más" menu instead of above the strip. */
  note?: string | null;
}

/** Quick mixes above the lanes. "Personalizado" lights up by itself once mute/solo is changed by hand. */
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
  exportOpen,
  onToggleExport,
  exportId,
  note = null,
}: MixBarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  const barRef = useRef<HTMLDivElement>(null);

  // Phone menu: Escape or a tap outside closes it. On wide screens the menu is always inline.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    const onPointer = (event: PointerEvent) => {
      if (barRef.current && !barRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [menuOpen]);

  return (
    <div className={styles.bar} ref={barRef}>
      <div className={`${styles.group} ${styles.presets}`} role="group" aria-label="Mezclas rápidas">
        {PRESETS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            className={styles.segment}
            aria-pressed={preset === id}
            disabled={disabled}
            onClick={() => onPreset(id)}
          >
            {label}
          </button>
        ))}
        <span
          className={styles.segment}
          data-custom={preset === "custom" ? "active" : "idle"}
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
          {PRESETS.map(({ id, label }) => (
            <option key={id} value={id}>
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
          <button
            type="button"
            className={styles.small}
            aria-expanded={exportOpen}
            aria-controls={exportId}
            onClick={() => {
              setMenuOpen(false);
              onToggleExport();
            }}
          >
            Exportar mi mezcla
          </button>
        </div>
        {!loopLabel && (
          <div className={styles.loop}>
            <p className={styles.hint}>Arrastrá sobre la regla para repetir un tramo.</p>
            <button
              type="button"
              className={styles.small}
              disabled={disabled || !canLoopSection}
              onClick={() => {
                setMenuOpen(false);
                onLoopSection();
              }}
            >
              Repetir esta sección
            </button>
          </div>
        )}
        {note && <p className={styles.note}>{note}</p>}
      </div>
      {loopLabel && (
        <div className={styles.loop}>
          <p className={`${styles.loopState} mono`}>Loop: {loopLabel}</p>
          <button type="button" className={styles.small} aria-keyshortcuts="L" onClick={onClearLoop}>
            Quitar loop
          </button>
        </div>
      )}
    </div>
  );
}
