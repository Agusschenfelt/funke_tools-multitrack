"use client";

import { useEffect, useState, useSyncExternalStore, type RefObject } from "react";
import type { EngineState, StudioEngine } from "@/lib/audio/engine";

export function useEngineState(engine: StudioEngine): EngineState {
  return useSyncExternalStore(engine.subscribe, engine.getSnapshot, engine.getServerSnapshot);
}

/**
 * Calls `apply(position)` every animation frame while mounted, skipping frames where nothing
 * moved. For DOM updates that must not go through React renders (playhead, readout).
 */
export function useFrame(engine: StudioEngine, apply: (position: number) => void) {
  useEffect(() => {
    let id = 0;
    let last = Number.NaN;
    const loop = () => {
      const position = engine.getPosition();
      if (position !== last) {
        last = position;
        apply(position);
      }
      id = requestAnimationFrame(loop);
    };
    id = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(id);
  }, [engine, apply]);
}

/** Content-box width of an element, tracked with a ResizeObserver. */
export function useWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
