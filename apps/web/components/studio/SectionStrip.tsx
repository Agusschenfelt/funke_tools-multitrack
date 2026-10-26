"use client";

import { useMemo, useRef } from "react";
import type { StudioEngine } from "@/lib/audio/engine";
import { barTicks, type StripGroup } from "@/lib/strip";
import { useWidth } from "./hooks";
import { Playhead } from "./Playhead";
import { seekFromClick } from "./Lane";
import styles from "./SectionStrip.module.css";

interface SectionStripProps {
  engine: StudioEngine;
  groups: readonly StripGroup[];
  downbeats: readonly number[];
  duration: number;
  activeGroup: number | null;
}

/**
 * The song's form as in a chord sheet: section names in capitals, repeats drawn `||: CORO :||`
 * with their count, bar numbers underneath. Read-only here; each section seeks to its start.
 */
export function SectionStrip({
  engine,
  groups,
  downbeats,
  duration,
  activeGroup,
}: SectionStripProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const width = useWidth(trackRef);
  const ticks = useMemo(
    () =>
      barTicks(
        downbeats,
        duration,
        width,
        groups.flatMap((g) => (g.startBar === null ? [] : [g.startBar])),
      ),
    [downbeats, duration, width, groups],
  );
  const pct = (seconds: number) => `${(seconds / duration) * 100}%`;

  return (
    <div className={styles.strip}>
      <div className={styles.corner} aria-hidden="true" />
      <div
        ref={trackRef}
        className={styles.track}
        role="group"
        aria-label="Secciones de la canción"
        onClick={(event) => {
          if (event.target === event.currentTarget) seekFromClick(event, engine, duration);
        }}
      >
        {duration > 0 &&
          groups.map((group, g) => {
            const repeated = group.count > 1;
            return (
              <button
                key={`${group.start}-${group.label}`}
                type="button"
                className={g === activeGroup ? `${styles.section} ${styles.active}` : styles.section}
                style={{ left: pct(group.start), width: pct(group.end - group.start) }}
                aria-current={g === activeGroup ? "true" : undefined}
                aria-label={
                  repeated
                    ? `${group.label}, se repite ${group.count} veces. Ir al inicio`
                    : `${group.label}. Ir al inicio`
                }
                onClick={() => engine.seek(group.start)}
              >
                {repeated && (
                  <span className={`${styles.sign} mono`} aria-hidden="true">
                    ||:
                  </span>
                )}
                <span className={styles.label}>{group.label}</span>
                {repeated && (
                  <>
                    <span className={`${styles.sign} mono`} aria-hidden="true">
                      :||
                    </span>
                    <span className={`${styles.times} mono`} aria-hidden="true">
                      ×{group.count}
                    </span>
                  </>
                )}
                {repeated &&
                  group.spans.slice(1).map((span) => (
                    <i
                      key={span.start}
                      className={styles.repeatLine}
                      aria-hidden="true"
                      style={{ left: `${((span.start - group.start) / (group.end - group.start)) * 100}%` }}
                    />
                  ))}
              </button>
            );
          })}
        <div className={styles.bars} aria-hidden="true">
          {duration > 0 &&
            ticks.map((tick) => (
              <span
                key={tick.bar}
                className={tick.anchor ? `${styles.bar} ${styles.barAnchor} mono` : `${styles.bar} mono`}
                style={{ left: pct(tick.time) }}
              >
                {tick.bar}
              </span>
            ))}
        </div>
        <Playhead engine={engine} duration={duration} />
      </div>
    </div>
  );
}
