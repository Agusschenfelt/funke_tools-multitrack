import { TASK_LABEL, formatElapsed, type RowView } from "@/lib/processing";
import { stageLine, stepView } from "@/lib/wait";
import styles from "./StageLines.module.css";

/**
 * One readable line per job: what is happening now, which step of how many, and how long it has
 * been. Rows keep their height whatever the text, so values change in place without a shift.
 */
export function StageLines({ rows }: { rows: RowView[] }) {
  return (
    <ul className={styles.list}>
      {rows.map((row) => {
        const { step, total } = stepView(row);
        const moving = row.status === "queued" || row.status === "running" || row.status === "checking";
        return (
          <li key={row.kind} className={styles.row} data-status={row.status}>
            <span className={styles.mark} aria-hidden="true" />
            <div className={styles.text}>
              <span className={styles.task}>{TASK_LABEL[row.kind]}</span>
              <span className={styles.line}>{stageLine(row)}</span>
            </div>
            <div className={`${styles.facts} mono`}>
              <span className={styles.step}>
                {step > 0 ? `${step}/${total}` : "–/–"}
                <span className="visually-hidden"> pasos</span>
              </span>
              <span className={styles.clock}>{moving || row.status === "finished" ? formatElapsed(row.seconds) : ""}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
