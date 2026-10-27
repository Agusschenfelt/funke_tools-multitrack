"use client";

import { useRef } from "react";
import type { StudioEngine } from "@/lib/audio/engine";
import { chipFitsLabel, type Chord } from "@/lib/chords";
import { useWidth } from "./hooks";
import { Playhead } from "./Playhead";
import { seekFromClick } from "./Lane";
import styles from "./ChordLane.module.css";

interface ChordLaneProps {
  engine: StudioEngine;
  chords: readonly Chord[];
  duration: number;
  /** Index of the chord under the playhead; -1 when none. */
  current: number;
}

/**
 * The song's chords as compact chips under the stem lanes, in chord-sheet mono. The chord under the
 * playhead is a neutral raised chip; orange stays with the playhead. A click anywhere seeks.
 */
export function ChordLane({ engine, chords, duration, current }: ChordLaneProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const width = useWidth(trackRef);
  if (duration <= 0 || chords.length === 0) return null;
  const pct = (seconds: number) => `${(seconds / duration) * 100}%`;
  return (
    <section className={styles.lane} aria-label="Acordes">
      <h2 className={styles.name}>Acordes</h2>
      <div
        ref={trackRef}
        className={styles.track}
        role="group"
        aria-label="Acordes de la canción"
        onClick={(event) => seekFromClick(event, engine, duration)}
      >
        {chords.map((chord, index) => {
          const chipPx = ((chord.end - chord.start) / duration) * width;
          return (
            <span
              key={`${chord.start}-${chord.label}`}
              className={index === current ? `${styles.chip} ${styles.current}` : styles.chip}
              style={{ left: pct(chord.start), width: pct(chord.end - chord.start) }}
              title={chord.label}
              aria-current={index === current ? "true" : undefined}
            >
              {chipFitsLabel(chord.label, chipPx) && (
                <span className={`${styles.label} mono`}>{chord.label}</span>
              )}
            </span>
          );
        })}
        <Playhead engine={engine} duration={duration} />
      </div>
    </section>
  );
}
