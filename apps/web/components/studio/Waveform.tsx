"use client";

import { useEffect, useRef, useState } from "react";
import type { Peaks } from "@/lib/audio/peaks";
import { rebucket } from "@/lib/audio/peaks";
import styles from "./Lane.module.css";

/** Peaks drawn on a canvas at device resolution; the colour comes from the CSS `color`. */
export function Waveform({ peaks, quiet }: { peaks: Peaks | null; quiet: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(([entry]) => {
      const ratio = window.devicePixelRatio || 1;
      setSize({
        width: Math.round(entry.contentRect.width * ratio),
        height: Math.round(entry.contentRect.height * ratio),
      });
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || size.width === 0 || size.height === 0) return;
    canvas.width = size.width;
    canvas.height = size.height;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, size.width, size.height);
    if (!peaks) return;
    context.fillStyle = getComputedStyle(canvas).color;
    const columns = rebucket(peaks.data, size.width);
    const middle = size.height / 2;
    const reach = (size.height / 2) * 0.92;
    for (let x = 0; x < size.width; x += 1) {
      const top = middle - Math.min(1, columns[x * 2 + 1] * peaks.scale) * reach;
      const bottom = middle - Math.max(-1, columns[x * 2] * peaks.scale) * reach;
      context.fillRect(x, top, 1, Math.max(1, bottom - top));
    }
  }, [peaks, size]);

  return (
    <canvas
      ref={canvasRef}
      className={quiet ? `${styles.canvas} ${styles.quiet}` : styles.canvas}
      aria-hidden="true"
    />
  );
}
