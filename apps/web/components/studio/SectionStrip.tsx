"use client";

import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { Section } from "@/lib/api";
import type { StudioEngine } from "@/lib/audio/engine";
import { barAt, moveBoundary, needsReview } from "@/lib/sections/edit";
import { barTicks, buildStrip, stripItems } from "@/lib/strip";
import { useWidth } from "./hooks";
import { Playhead } from "./Playhead";
import { seekFromClick } from "./Lane";
import styles from "./SectionStrip.module.css";

const ESTIMATED_ID = "estimated-grid-legend";
export const ESTIMATED_GRID_LEGEND = "Grilla estimada (intro sin pulso claro)";

interface SectionStripProps {
  engine: StudioEngine;
  sections: readonly Section[];
  downbeats: readonly number[];
  /** Seconds before which the grid is estimated (beatless intro); null when it was all detected. */
  estimatedUntil?: number | null;
  duration: number;
  /** Flat index of the section under the playhead. */
  activeIndex: number | null;
  selected: number | null;
  editedOnServer: boolean;
  onSelect: (index: number) => void;
  /** Seek to the section and play (double-click or Enter). */
  onPlay: (index: number) => void;
  onMove: (index: number, time: number) => void;
  onNudge: (index: number, bars: number) => void;
}

/**
 * The song's form as in a chord sheet: section names in capitals, repeats drawn `||: CORO :||`
 * with their count, bar numbers underneath. Each section is selectable; the edge between two
 * sections is a slider that drags (or arrow-keys) one bar at a time and shows its bar number.
 */
export function SectionStrip({
  engine,
  sections,
  downbeats,
  estimatedUntil = null,
  duration,
  activeIndex,
  selected,
  editedOnServer,
  onSelect,
  onPlay,
  onMove,
  onNudge,
}: SectionStripProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const width = useWidth(trackRef);
  const [drag, setDrag] = useState<{ index: number; time: number } | null>(null);
  // A press arms an edge; only a move starts the drag, so a plain click never shifts it.
  const armed = useRef<number | null>(null);

  // While an edge is dragged the strip draws the snapped preview; nothing is committed yet.
  const shown = useMemo<readonly Section[]>(
    () => (drag ? (moveBoundary(sections, drag.index, drag.time, downbeats)?.sections ?? sections) : sections),
    [sections, drag, downbeats],
  );
  const groups = useMemo(() => buildStrip(shown, downbeats, duration), [shown, downbeats, duration]);
  const items = useMemo(() => stripItems(groups), [groups]);
  const ticks = useMemo(
    () =>
      barTicks(
        downbeats,
        duration,
        width,
        groups.flatMap((g) => (g.startBar === null ? [] : [g.startBar])),
        undefined,
        estimatedUntil,
      ),
    [downbeats, duration, width, groups, estimatedUntil],
  );
  const pct = (seconds: number) => `${(seconds / duration) * 100}%`;
  const canMove = downbeats.length > 0;

  const timeAt = (event: PointerEvent<HTMLElement>): number | null => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return null;
    return Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)) * duration;
  };

  const onHandleKey = (index: number, event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape" && drag) {
      armed.current = null;
      setDrag(null);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      onNudge(index, event.key === "ArrowLeft" ? -1 : 1);
    }
  };

  return (
    <div className={styles.strip}>
      <div className={styles.corner} aria-hidden="true" />
      <div
        ref={trackRef}
        className={styles.track}
        role="group"
        aria-label="Secciones de la canción"
        aria-describedby={estimatedUntil ? ESTIMATED_ID : undefined}
        onClick={(event) => {
          if (event.target === event.currentTarget) seekFromClick(event, engine, duration);
        }}
      >
        {duration > 0 &&
          items.map((item) => {
            const section = shown[item.index];
            const repeated = item.count > 1;
            const review = section ? needsReview(section, editedOnServer) : false;
            const classes = [styles.section];
            if (item.index === activeIndex) classes.push(styles.active);
            if (item.index === selected) classes.push(styles.selected);
            return (
              <button
                key={item.index}
                type="button"
                className={classes.join(" ")}
                style={{ left: pct(item.start), width: pct(item.end - item.start) }}
                aria-pressed={item.index === selected}
                aria-current={item.index === activeIndex ? "true" : undefined}
                aria-label={`${item.label}${repeated ? `, se repite ${item.count} veces` : ""}${review ? ", conviene revisar" : ""}. Enter para escuchar`}
                onClick={() => onSelect(item.index)}
                onDoubleClick={() => onPlay(item.index)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    onPlay(item.index);
                  }
                }}
              >
                {repeated && item.first && (
                  <span className={`${styles.sign} mono`} aria-hidden="true">
                    ||:
                  </span>
                )}
                <span className={styles.label}>{item.label}</span>
                {review && <span className={`${styles.review} mono`}>revisar</span>}
                {repeated && item.last && (
                  <>
                    <span className={`${styles.sign} mono`} aria-hidden="true">
                      :||
                    </span>
                    <span className={`${styles.times} mono`} aria-hidden="true">
                      ×{item.count}
                    </span>
                  </>
                )}
                {repeated && !item.first && <i className={styles.repeatLine} aria-hidden="true" />}
              </button>
            );
          })}
        {duration > 0 &&
          canMove &&
          items.slice(1).map((item) => {
            const dragging = drag?.index === item.index;
            const bar = barAt(downbeats, shown[item.index]?.start ?? 0);
            return (
              <div
                key={`edge-${item.index}`}
                className={dragging ? `${styles.edge} ${styles.edgeDragging}` : styles.edge}
                style={{ left: pct(item.start) }}
                role="slider"
                tabIndex={0}
                aria-orientation="horizontal"
                aria-label={`Límite entre ${items[item.index - 1].label} y ${item.label}`}
                aria-valuemin={1}
                aria-valuemax={downbeats.length}
                aria-valuenow={bar ?? undefined}
                aria-valuetext={bar === null ? undefined : `compás ${bar}`}
                aria-keyshortcuts="ArrowLeft ArrowRight"
                onKeyDown={(event) => onHandleKey(item.index, event)}
                onPointerDown={(event) => {
                  if (event.button !== 0) return;
                  event.currentTarget.setPointerCapture(event.pointerId);
                  armed.current = item.index;
                }}
                onPointerMove={(event) => {
                  if (armed.current !== item.index) return;
                  const time = timeAt(event);
                  if (time !== null) setDrag({ index: item.index, time });
                }}
                onPointerUp={() => {
                  if (drag?.index === item.index) onMove(item.index, drag.time);
                  armed.current = null;
                  setDrag(null);
                }}
                onPointerCancel={() => {
                  armed.current = null;
                  setDrag(null);
                }}
              >
                <i className={styles.grip} aria-hidden="true" />
                {dragging && bar !== null && (
                  <span className={`${styles.tip} mono`} aria-hidden="true">
                    Compás {bar}
                  </span>
                )}
              </div>
            );
          })}
        {estimatedUntil ? (
          <span id={ESTIMATED_ID} className="visually-hidden">
            {ESTIMATED_GRID_LEGEND}
          </span>
        ) : null}
        <div className={styles.bars} aria-hidden="true">
          {duration > 0 && estimatedUntil ? (
            <span
              className={styles.estimated}
              style={{ width: pct(Math.min(estimatedUntil, duration)) }}
              title={ESTIMATED_GRID_LEGEND}
            />
          ) : null}
          {duration > 0 &&
            ticks.map((tick) => (
              <span
                key={tick.bar}
                className={[
                  styles.bar,
                  tick.anchor ? styles.barAnchor : "",
                  tick.estimated ? styles.barEstimated : "",
                  "mono",
                ]
                  .filter(Boolean)
                  .join(" ")}
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
