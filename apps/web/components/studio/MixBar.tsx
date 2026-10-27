"use client";

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
}: MixBarProps) {
  return (
    <div className={styles.bar}>
      <div className={styles.group} role="group" aria-label="Mezclas rápidas">
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
      <div className={styles.loop}>
        {loopLabel ? (
          <>
            <p className={`${styles.loopState} mono`}>Loop: {loopLabel}</p>
            <button type="button" className={styles.small} aria-keyshortcuts="L" onClick={onClearLoop}>
              Quitar loop
            </button>
          </>
        ) : (
          <>
            <p className={styles.hint}>Arrastrá sobre la regla para repetir un tramo.</p>
            <button
              type="button"
              className={styles.small}
              disabled={disabled || !canLoopSection}
              onClick={onLoopSection}
            >
              Repetir esta sección
            </button>
          </>
        )}
      </div>
    </div>
  );
}
