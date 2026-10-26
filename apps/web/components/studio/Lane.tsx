"use client";

import type { MouseEvent } from "react";
import type { StemView } from "@/lib/audio/engine";
import type { StudioEngine } from "@/lib/audio/engine";
import type { StemMix } from "@/lib/audio/mix";
import { STEM_LABEL, type StemName } from "@/lib/audio/stems";
import { formatBytes } from "@/lib/format";
import type { StripSpan } from "@/lib/strip";
import { Playhead } from "./Playhead";
import { Waveform } from "./Waveform";
import styles from "./Lane.module.css";

interface LaneProps {
  engine: StudioEngine;
  name: StemName;
  view: StemView;
  mix: StemMix;
  /** Whether the current mute/solo state lets this stem sound. */
  audible: boolean;
  duration: number;
  activeSpan: StripSpan | null;
  index: number;
  count: number;
}

export function seekFromClick(event: MouseEvent<HTMLElement>, engine: StudioEngine, duration: number) {
  const rect = event.currentTarget.getBoundingClientRect();
  if (rect.width === 0) return;
  const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
  engine.seek(fraction * duration);
}

function loadingText(view: StemView): string | null {
  if (view.phase === "ready") return null;
  if (view.phase === "downloading") {
    return view.loaded > 0 ? `Descargando ${formatBytes(view.loaded)}` : "Descargando…";
  }
  if (view.phase === "decoding") return "Decodificando…";
  if (view.phase === "error") {
    return view.failure === "decode" ? "No se pudo leer esta pista" : "No se pudo descargar esta pista";
  }
  return "En espera";
}

export function Lane({
  engine,
  name,
  view,
  mix,
  audible,
  duration,
  activeSpan,
  index,
  count,
}: LaneProps) {
  const label = STEM_LABEL[name];
  const status = loadingText(view);
  return (
    <section className={styles.lane} aria-label={label}>
      <div className={styles.head}>
        <h3 className={styles.name}>{label}</h3>
        <span className={`${styles.pager} mono`} aria-hidden="true">
          {index + 1} / {count}
        </span>
        <div className={styles.buttons}>
          <button
            type="button"
            className={styles.toggle}
            aria-pressed={mix.muted}
            aria-label={`Silenciar ${label}`}
            onClick={() => engine.toggleMute(name)}
          >
            M
          </button>
          <button
            type="button"
            className={styles.toggle}
            aria-pressed={mix.solo}
            aria-label={`Solo ${label}`}
            onClick={() => engine.toggleSolo(name)}
          >
            S
          </button>
        </div>
        <input
          type="range"
          className={styles.volume}
          min={0}
          max={1}
          step={0.01}
          value={mix.volume}
          aria-label={`Volumen de ${label}`}
          onChange={(event) => engine.setVolume(name, Number(event.target.value))}
        />
      </div>
      <div
        className={styles.wave}
        onClick={(event) => seekFromClick(event, engine, duration)}
      >
        <Waveform peaks={view.peaks} quiet={!audible} />
        {activeSpan && duration > 0 && (
          <span
            className={styles.tint}
            aria-hidden="true"
            style={{
              left: `${(activeSpan.start / duration) * 100}%`,
              width: `${((activeSpan.end - activeSpan.start) / duration) * 100}%`,
            }}
          />
        )}
        {status && (
          <p className={`${styles.loading} mono`} role="status">
            {status}
          </p>
        )}
        <Playhead engine={engine} duration={duration} />
      </div>
    </section>
  );
}
