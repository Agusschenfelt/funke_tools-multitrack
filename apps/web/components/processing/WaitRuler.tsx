import { RULER_BARS } from "@/lib/wait";
import styles from "./WaitRuler.module.css";

interface WaitRulerProps {
  /** 1-based bar holding the orange mark. */
  current: number;
  /** Bars already behind the mark. */
  passed: number;
  finished: boolean;
  /** Both jobs are moving or waiting: the mark ticks. */
  active: boolean;
  /** Completed steps of the total, for assistive tech. */
  valueNow: number;
  valueMax: number;
}

/**
 * The upload screen's 1-12 ruler, reused as the wait's clock: the orange mark sits on the bar the
 * work has reached and moves only when a stage completes. Bars behind it turn to paper.
 */
export function WaitRuler({ current, passed, finished, active, valueNow, valueMax }: WaitRulerProps) {
  const bars = Array.from({ length: RULER_BARS }, (_, index) => index + 1);
  return (
    <div
      className={styles.ruler}
      data-finished={finished || undefined}
      role="progressbar"
      aria-label="Avance del procesamiento"
      aria-valuemin={0}
      aria-valuemax={valueMax}
      aria-valuenow={valueNow}
      aria-valuetext={finished ? "Todo listo" : `Paso ${Math.min(valueNow + 1, valueMax)} de ${valueMax}`}
    >
      <div className={styles.bars} aria-hidden="true">
        {bars.map((bar) => (
          <span
            key={bar}
            className={styles.bar}
            data-passed={bar <= passed || undefined}
            data-current={bar === current || undefined}
            data-tick={(bar === current && active && !finished) || undefined}
          />
        ))}
      </div>
      <div className={`${styles.numbers} mono`} aria-hidden="true">
        {bars.map((bar) => (
          <span key={bar} data-current={bar === current || undefined}>
            {bar}
          </span>
        ))}
      </div>
    </div>
  );
}
