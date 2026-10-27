"use client";

import { useEffect, useRef, useState } from "react";
import { reduceWindowDrag, type WindowDragInput } from "@/lib/fileDrag";

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
    const apply = (input: WindowDragInput, event: Event) => {
      const result = reduceWindowDrag(depth.current, enabled, input);
      depth.current = result.depth;
      setVisible(result.visible);
      // Required for the drop event to fire; also stops the browser navigating to the file.
      if (result.preventDefault) event.preventDefault();
      if (result.file) handler.current(result.file);
    };
    const onEnter = (event: DragEvent) => apply({ kind: "enter", types: event.dataTransfer?.types }, event);
    const onLeave = (event: DragEvent) => apply({ kind: "leave", types: event.dataTransfer?.types }, event);
    const onOver = (event: DragEvent) => apply({ kind: "over", types: event.dataTransfer?.types }, event);
    const onDrop = (event: DragEvent) =>
      apply({ kind: "drop", types: event.dataTransfer?.types, file: event.dataTransfer?.files[0] ?? null }, event);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") apply({ kind: "escape" }, event);
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
