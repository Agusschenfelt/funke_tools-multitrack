"use client";

import { useCallback, useRef } from "react";
import type { StudioEngine } from "@/lib/audio/engine";
import { useFrame } from "./hooks";
import styles from "./Lane.module.css";

/** The orange mark. Moved straight on the DOM each frame, outside React renders. */
export function Playhead({ engine, duration }: { engine: StudioEngine; duration: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const apply = useCallback(
    (position: number) => {
      const element = ref.current;
      if (element && duration > 0) element.style.left = `${(position / duration) * 100}%`;
    },
    [duration],
  );
  useFrame(engine, apply);
  return <span ref={ref} className={styles.playhead} aria-hidden="true" />;
}
