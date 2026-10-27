import styles from "./BarProgress.module.css";

const BARS = 12;

interface BarProgressProps {
  /** 0..1 while a transfer runs; null renders the empty staff as decoration only. */
  fraction: number | null;
  label?: string;
}

/** A row of numbered bars. Progress fills it left to right like a take being played through. */
export function BarProgress({ fraction, label }: BarProgressProps) {
  const percent = fraction === null ? 0 : Math.round(Math.min(1, Math.max(0, fraction)) * 100);
  const bars = Array.from({ length: BARS }, (_, index) => index + 1);
  const meterProps =
    fraction === null
      ? { "aria-hidden": true as const }
      : {
          role: "progressbar" as const,
          "aria-label": label,
          "aria-valuemin": 0,
          "aria-valuemax": 100,
          "aria-valuenow": percent,
        };

  return (
    <div className={styles.staff} {...meterProps}>
      <div className={styles.bars}>
        {bars.map((bar) => (
          <span key={bar} className={styles.bar} />
        ))}
        {fraction !== null && <span className={styles.fill} style={{ width: `${percent}%` }} />}
      </div>
      <div className={`${styles.numbers} mono`} aria-hidden="true">
        {bars.map((bar) => (
          <span key={bar}>{bar}</span>
        ))}
      </div>
    </div>
  );
}
