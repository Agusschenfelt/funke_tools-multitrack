import { MAX_UPLOAD_MB, formatsLabel, limitLabel } from "@/lib/upload";
import styles from "./DropOverlay.module.css";

/** Full-viewport layer shown while a file is dragged over the window. Drops are caught on window. */
export function DropOverlay({ open }: { open: boolean }) {
  return (
    <>
      <p className="visually-hidden" role="status" aria-live="polite">
        {open ? "Soltá el archivo para subir tu tema." : ""}
      </p>
      {open && (
        <div className={styles.overlay} aria-hidden="true">
          <div className={styles.frame}>
            <svg className={styles.icon} viewBox="0 0 48 48" width="48" height="48" fill="none">
              <path
                d="M24 6v26M12 22l12 12 12-12M8 42h32"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="square"
              />
            </svg>
            <p className={styles.message}>Soltá tu tema acá</p>
            <p className={styles.constraints}>
              {formatsLabel()}. Hasta {MAX_UPLOAD_MB} MB y {limitLabel()}.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
