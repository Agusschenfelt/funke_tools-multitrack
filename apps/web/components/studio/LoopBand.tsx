import type { LoopRange } from "@/lib/audio/loop";
import styles from "./LoopBand.module.css";

/** The repeated stretch, in neutral ink (orange stays with the playhead and the active section). */
export function LoopBand({
  range,
  duration,
  preview = false,
}: {
  range: LoopRange | null;
  duration: number;
  /** Being dragged, not yet applied. */
  preview?: boolean;
}) {
  if (!range || duration <= 0) return null;
  return (
    <span
      className={styles.band}
      data-preview={preview ? "" : undefined}
      aria-hidden="true"
      style={{
        left: `${(range.start / duration) * 100}%`,
        width: `${((range.end - range.start) / duration) * 100}%`,
      }}
    />
  );
}
