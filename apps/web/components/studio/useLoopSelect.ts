import { useEffect, useRef, useState, type PointerEvent, type RefObject } from "react";
import type { StudioEngine } from "@/lib/audio/engine";
import { snapLoop, type LoopRange } from "@/lib/audio/loop";

/** A press that moves less than this is a click (seek), not a drag (loop). */
const DRAG_PX = 4;

interface Options {
  engine: StudioEngine;
  duration: number;
  downbeats: readonly number[];
  /** Element whose width maps to the whole song. */
  area: RefObject<HTMLElement | null>;
}

/**
 * Pointer handlers for a ruler or minimap: a click seeks, a drag selects a range that snaps to
 * bars (hold Alt/Option to drag freely) and starts looping it on release. Escape drops a drag.
 */
export function useLoopSelect({ engine, duration, downbeats, area }: Options) {
  const [preview, setPreview] = useState<LoopRange | null>(null);
  const press = useRef<{ x: number; time: number; dragging: boolean } | null>(null);

  const timeAt = (clientX: number): number | null => {
    const rect = area.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return null;
    return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)) * duration;
  };
  const rangeFor = (event: PointerEvent<HTMLElement>): LoopRange | null => {
    const from = press.current?.time;
    const to = timeAt(event.clientX);
    if (from === undefined || to === null) return null;
    return snapLoop(from, to, { downbeats, duration, snap: !event.altKey });
  };
  const cancel = () => {
    press.current = null;
    setPreview(null);
  };

  useEffect(() => {
    if (!preview) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [preview]);

  return {
    preview,
    handlers: {
      onPointerDown(event: PointerEvent<HTMLElement>) {
        if (event.button !== 0 || duration <= 0) return;
        const time = timeAt(event.clientX);
        if (time === null) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        press.current = { x: event.clientX, time, dragging: false };
      },
      onPointerMove(event: PointerEvent<HTMLElement>) {
        const current = press.current;
        if (!current) return;
        if (!current.dragging && Math.abs(event.clientX - current.x) < DRAG_PX) return;
        current.dragging = true;
        setPreview(rangeFor(event));
      },
      onPointerUp(event: PointerEvent<HTMLElement>) {
        const current = press.current;
        if (!current) return;
        if (current.dragging) {
          const range = rangeFor(event);
          if (range) engine.setLoop(range);
        } else {
          const time = timeAt(event.clientX);
          if (time !== null) engine.seek(time);
        }
        cancel();
      },
      onPointerCancel: cancel,
    },
  };
}
