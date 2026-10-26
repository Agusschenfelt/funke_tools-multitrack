import {
  TASK_LABEL,
  formatElapsed,
  stageLabel,
  statusLabel,
  type RowView,
} from "@/lib/processing";
import styles from "./JobTable.module.css";

/**
 * Job queue as a fixed-column table. Columns never resize: only the cell text changes, so a
 * stage or status change causes no layout shift.
 */
export function JobTable({ rows }: { rows: RowView[] }) {
  return (
    <table className={styles.table}>
      <caption className="visually-hidden">Procesos de la canción</caption>
      <colgroup>
        <col className={styles.colTask} />
        <col className={styles.colStage} />
        <col className={styles.colStatus} />
        <col className={styles.colTime} />
      </colgroup>
      <thead>
        <tr>
          <th scope="col">Tarea</th>
          <th scope="col">Etapa</th>
          <th scope="col">Estado</th>
          <th scope="col" className={styles.num}>
            Tiempo
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.kind} className={styles.row} data-status={row.status}>
            <th scope="row">{TASK_LABEL[row.kind]}</th>
            <td>{row.status === "untracked" ? "—" : stageLabel(row.stage)}</td>
            <td>
              <span className={styles.mark} aria-hidden="true" />
              {row.status === "untracked" ? "Sin datos" : statusLabel(row.status)}
            </td>
            <td className={`${styles.num} mono`}>{formatElapsed(row.seconds)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
