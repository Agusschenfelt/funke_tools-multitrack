"use client";

import { useCallback, useRef, type KeyboardEvent, type MouseEvent } from "react";
import type { StudioEngine } from "@/lib/audio/engine";
import { upperBound } from "@/lib/audio/grid";
import { formatClock } from "@/lib/audio/grid";
import type { StripGroup } from "@/lib/strip";
import { useFrame } from "./hooks";
import { Playhead } from "./Playhead";
import styles from "./Transport.module.css";

/** The whole song at a glance, sections to scale. Click to seek; arrow keys move a bar. */
export function Minimap({
  engine,
  groups,
  downbeats,
  duration,
  activeGroup,
}: {
  engine: StudioEngine;
  groups: readonly StripGroup[];
  downbeats: readonly number[];
  duration: number;
  activeGroup: number | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Assistive technology reads the position from attributes kept current outside React renders.
  const announce = useCallback((position: number) => {
    ref.current?.setAttribute("aria-valuenow", String(Math.round(position)));
    ref.current?.setAttribute("aria-valuetext", formatClock(position));
  }, []);
  useFrame(engine, announce);

  const seek = (event: MouseEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    engine.seek(Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)) * duration);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const now = engine.getPosition();
    const bars = upperBound(downbeats, now + 1e-3);
    if (event.key === "ArrowRight") {
      engine.seek(downbeats[bars] ?? duration);
    } else if (event.key === "ArrowLeft") {
      // Back to the start of this bar, or the previous one when already there.
      const here = downbeats[bars - 1];
      engine.seek(here !== undefined && now - here > 1 ? here : (downbeats[bars - 2] ?? 0));
    } else if (event.key === "Home") {
      engine.seek(0);
    } else if (event.key === "End") {
      engine.seek(duration);
    } else {
      return;
    }
    event.preventDefault();
  };

  return (
    <div
      ref={ref}
      className={styles.minimap}
      role="slider"
      tabIndex={0}
      aria-label="Posición en la canción"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={0}
      onClick={seek}
      onKeyDown={onKeyDown}
    >
      {duration > 0 &&
        groups.map((group, g) => (
          <span
            key={`${group.start}-${group.label}`}
            className={g === activeGroup ? `${styles.mapSection} ${styles.mapActive}` : styles.mapSection}
            style={{
              left: `${(group.start / duration) * 100}%`,
              width: `${((group.end - group.start) / duration) * 100}%`,
            }}
            aria-hidden="true"
          />
        ))}
      <Playhead engine={engine} duration={duration} />
    </div>
  );
}
