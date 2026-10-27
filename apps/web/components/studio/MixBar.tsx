"use client";

import { CUSTOM_LABEL, PRESETS, type MixPreset, type PresetId } from "@/lib/audio/presets";
import styles from "./MixBar.module.css";

interface MixBarProps {
  preset: MixPreset;
  disabled: boolean;
  onPreset: (id: PresetId) => void;
}

/** Quick mixes above the lanes. "Personalizado" lights up by itself once mute/solo is changed by hand. */
export function MixBar({ preset, disabled, onPreset }: MixBarProps) {
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
    </div>
  );
}
