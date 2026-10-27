import type { PackFile } from "@/lib/export/pack";
import styles from "./ExportView.module.css";

/** The ZIP's name and file list for the current choices. Mirrors the server (see lib/export/pack.ts). */
export function PackPreview({
  zip,
  files,
  detail,
}: {
  zip: string;
  files: PackFile[];
  detail: string;
}) {
  return (
    <section className={styles.preview} aria-labelledby="preview-title">
      <h2 id="preview-title" className={styles.heading}>
        Qué trae el ZIP
      </h2>
      <p className={`${styles.zip} mono`}>{zip}</p>
      <p className={styles.hint}>{detail}</p>
      <ul className={styles.files}>
        {files.map((file) => (
          <li key={file.name}>
            <span className="mono">{file.name}</span>
            <span className={styles.fileNote}>{file.note}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
