"use client";

import { useCallback, useRef, type KeyboardEvent } from "react";
import type { StudioEngine } from "@/lib/audio/engine";
import { formatClock } from "@/lib/audio/grid";
import { minimapSeekTarget } from "@/lib/audio/minimapKeys";
import type { LoopRange } from "@/lib/audio/loop";
import type { StripGroup } from "@/lib/strip";
import { useFrame } from "./hooks";
import { LoopBand } from "./LoopBand";
import { Playhead } from "./Playhead";
import { useLoopSelect } from "./useLoopSelect";
import styles from "./Transport.module.css";

/**
 * The whole song at a glance, sections to scale. Click to seek, drag to loop a range of bars
 * (Alt/Option: free); arrows move a bar, Page keys four.
 */
export function Minimap({
  engine,
  groups,
  downbeats,
  duration,
  activeGroup,
  loop,
}: {
  engine: StudioEngine;
  groups: readonly StripGroup[];
  downbeats: readonly number[];
  duration: number;
  activeGroup: number | null;
  loop: LoopRange | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Assistive technology reads the position from attributes kept current outside React renders.
  const announce = useCallback((position: number) => {
    ref.current?.setAttribute("aria-valuenow", String(Math.round(position)));
    ref.current?.setAttribute("aria-valuetext", formatClock(position));
  }, []);
  useFrame(engine, announce);

  const select = useLoopSelect({ engine, duration, downbeats, area: ref });

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = minimapSeekTarget(event.key, {
      now: engine.getPosition(),
      downbeats,
      duration,
    });
    if (target === null) return;
    engine.seek(target);
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
      onKeyDown={onKeyDown}
      {...select.handlers}
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
      <LoopBand range={select.preview ?? loop} duration={duration} preview={select.preview !== null} />
      <Playhead engine={engine} duration={duration} />
    </div>
  );
}
