"use client";

import type { KeyboardEvent, MouseEvent } from "react";
import type { StemView } from "@/lib/audio/engine";
import type { StudioEngine } from "@/lib/audio/engine";
import { panText, type StemMix } from "@/lib/audio/mix";
import type { LoopRange } from "@/lib/audio/loop";
import { STEM_LABEL, type StemName } from "@/lib/audio/stems";
import { formatBytes } from "@/lib/format";
import type { StripSpan } from "@/lib/strip";
import { LoopBand } from "./LoopBand";
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
  loop: LoopRange | null;
  /** Signed link to the full-quality WAV of this stem; absent when the song has none. */
  downloadUrl?: string;
  /** File name offered by the browser. */
  downloadName?: string;
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

/** Left-centre-right. Double-click or Enter puts it back in the centre. */
function PanControl({ engine, name, label, pan }: { engine: StudioEngine; name: StemName; label: string; pan: number }) {
  const centre = () => engine.setPan(name, 0);
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    centre();
  };
  return (
    <div className={styles.pan}>
      <span className={`${styles.panEnd} mono`} aria-hidden="true">
        L
      </span>
      <input
        type="range"
        className={styles.panSlider}
        min={-1}
        max={1}
        step={0.1}
        value={pan}
        aria-label={`Paneo de ${label}`}
        aria-valuetext={panText(pan)}
        aria-keyshortcuts="Enter"
        title="Doble clic o Enter para centrar"
        onChange={(event) => engine.setPan(name, Number(event.target.value))}
        onDoubleClick={centre}
        onKeyDown={onKeyDown}
      />
      <span className={`${styles.panEnd} mono`} aria-hidden="true">
        R
      </span>
    </div>
  );
}

export function Lane({
  engine,
  name,
  view,
  mix,
  audible,
  duration,
  activeSpan,
  loop,
  downloadUrl,
  downloadName,
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
          {downloadUrl && (
            <a
              className={styles.toggle}
              href={downloadUrl}
              download={downloadName}
              aria-label={`Descargar ${label} (WAV)`}
              title={`Descargar ${label} (WAV)`}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
                <path
                  d="M12 4v11m0 0l-4.5-4.5M12 15l4.5-4.5M5 19h14"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="square"
                />
              </svg>
            </a>
          )}
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
        <PanControl engine={engine} name={name} label={label} pan={mix.pan} />
      </div>
      <div
        className={styles.wave}
        onClick={(event) => seekFromClick(event, engine, duration)}
      >
        <Waveform peaks={view.peaks} quiet={!audible} />
        <LoopBand range={loop} duration={duration} />
        {activeSpan && duration > 0 && (
          <span
            className={styles.mark}
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
