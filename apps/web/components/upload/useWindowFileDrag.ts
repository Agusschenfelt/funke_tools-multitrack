"use client";

import { useEffect, useRef, useState } from "react";
import { dragHasFiles, isOverlayVisible, nextDragDepth, type DragStep } from "@/lib/fileDrag";

/**
 * Tracks a file drag anywhere over the window. Returns whether the overlay shows; a drop anywhere
 * hands the first file to `onFile`. While `enabled` is false drags are ignored (and the browser
 * keeps its default of opening the file, which we cancel to avoid leaving the page).
 */
export function useWindowFileDrag(onFile: (file: File) => void, enabled: boolean): boolean {
  const [visible, setVisible] = useState(false);
  const depth = useRef(0);
  const handler = useRef(onFile);

  useEffect(() => {
    handler.current = onFile;
  });

  useEffect(() => {
    const step = (kind: DragStep) => {
      depth.current = nextDragDepth(depth.current, kind);
      setVisible(isOverlayVisible(depth.current));
    };
    const isFileDrag = (event: DragEvent) => dragHasFiles(event.dataTransfer?.types);

    const onEnter = (event: DragEvent) => {
      if (isFileDrag(event) && enabled) step("enter");
    };
    const onLeave = (event: DragEvent) => {
      if (isFileDrag(event) && enabled) step("leave");
    };
    const onOver = (event: DragEvent) => {
      // Required for the drop event to fire; also stops the browser navigating to the file.
      if (isFileDrag(event)) event.preventDefault();
    };
    const onDrop = (event: DragEvent) => {
      if (!isFileDrag(event)) return;
      event.preventDefault();
      step("reset");
      const file = event.dataTransfer?.files[0];
      if (file && enabled) handler.current(file);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") step("reset");
    };

    window.addEventListener("dragenter", onEnter);
    window.addEventListener("dragleave", onLeave);
    window.addEventListener("dragover", onOver);
    window.addEventListener("drop", onDrop);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("dragenter", onEnter);
      window.removeEventListener("dragleave", onLeave);
      window.removeEventListener("dragover", onOver);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("keydown", onKey);
      depth.current = 0;
    };
  }, [enabled]);

  return visible && enabled;
}
