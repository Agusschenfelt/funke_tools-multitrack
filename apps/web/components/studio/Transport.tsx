"use client";

import { useCallback, useRef } from "react";
import type { CueLanguage, EngineState, StudioEngine } from "@/lib/audio/engine";
import { barPosition, COUNT_IN_LABEL, formatBarBeat, formatClock } from "@/lib/audio/grid";
import type { StripGroup } from "@/lib/strip";
import { useFrame } from "./hooks";
import { Minimap } from "./Minimap";
import styles from "./Transport.module.css";

interface TransportProps {
  engine: StudioEngine;
  state: EngineState;
  groups: readonly StripGroup[];
  beats: readonly number[];
  downbeats: readonly number[];
  perBar: number;
  duration: number;
  activeGroup: number | null;
  hasGrid: boolean;
  /** Chord under the playhead and the one after it; null without chords. */
  currentChord?: string | null;
  nextChord?: string | null;
}

function PlayIcon({ playing }: { playing: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">
      {playing ? (
        <path d="M6 4h4v16H6zM14 4h4v16h-4z" fill="currentColor" />
      ) : (
        <path d="M7 4l13 8-13 8z" fill="currentColor" />
      )}
    </svg>
  );
}

export function Transport({
  engine,
  state,
  groups,
  beats,
  downbeats,
  perBar,
  duration,
  activeGroup,
  hasGrid,
  currentChord = null,
  nextChord = null,
}: TransportProps) {
  const barRef = useRef<HTMLSpanElement>(null);
  const clockRef = useRef<HTMLSpanElement>(null);
  const ready = state.status === "ready";

  const apply = useCallback(
    (position: number) => {
      if (barRef.current) {
        const text = hasGrid
          ? formatBarBeat(barPosition(position, beats, downbeats, perBar))
          : "—";
        barRef.current.textContent = text;
        // The word "Cuenta" is set smaller than the bar:beat numerals so it fits the same slot.
        if (text === COUNT_IN_LABEL) barRef.current.dataset.word = "";
        else delete barRef.current.dataset.word;
      }
      if (clockRef.current) clockRef.current.textContent = formatClock(position);
    },
    [beats, downbeats, perBar, hasGrid],
  );
  useFrame(engine, apply);

  return (
    <div className={styles.transport}>
      <Minimap
        engine={engine}
        groups={groups}
        downbeats={downbeats}
        duration={duration}
        activeGroup={activeGroup}
        loop={state.loop}
      />
      <div className={styles.controls}>
        <button
          type="button"
          className={styles.play}
          disabled={!ready}
          aria-label={state.playing ? "Pausar" : "Reproducir"}
          aria-keyshortcuts="Space"
          onClick={engine.toggle}
        >
          <PlayIcon playing={state.playing} />
        </button>

        <p className={styles.readout}>
          <span className="visually-hidden">Compás y tiempo: </span>
          <span ref={barRef} className={`${styles.bars} mono`}>
            —
          </span>
          <span className={styles.sub}>
            <span className={`${styles.clock} mono`}>
              <span ref={clockRef}>0:00</span>
              <span className={styles.total}> / {formatClock(duration)}</span>
            </span>
            {currentChord !== null && (
              <span className={styles.chords}>
                <span className="visually-hidden">Acorde: </span>
                <span className={`${styles.chord} mono`}>{currentChord}</span>
                {nextChord !== null && (
                  <span className={styles.next}>
                    Sigue <span className="mono">{nextChord}</span>
                  </span>
                )}
              </span>
            )}
          </span>
        </p>

        <div className={styles.toggles}>
          <button
            type="button"
            className={styles.toggle}
            aria-pressed={state.clickOn}
            disabled={!hasGrid}
            onClick={() => engine.setClick(!state.clickOn)}
          >
            Click
          </button>
          <button
            type="button"
            className={styles.toggle}
            aria-pressed={state.cuesOn}
            disabled={!hasGrid}
            onClick={() => engine.setCues(!state.cuesOn)}
          >
            Guías
          </button>
          <select
            className={styles.language}
            aria-label="Idioma de las guías"
            value={state.cueLanguage}
            onChange={(event) => engine.setCueLanguage(event.target.value as CueLanguage)}
          >
            <option value="es">ES</option>
            <option value="en">EN</option>
          </select>
        </div>
      </div>
      {state.cuesOn && state.cuesStatus === "error" && (
        <p className={styles.note} role="status">
          No se pudieron cargar las guías habladas.
        </p>
      )}
    </div>
  );
}
