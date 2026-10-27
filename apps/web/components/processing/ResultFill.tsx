import type { Analysis, Section } from "@/lib/api";
import { keyLabel } from "@/lib/chords";
import { formatDuration } from "@/lib/processing";
import { chordsSummary, sectionRuns } from "@/lib/wait";
import styles from "./ResultFill.module.css";

export interface PartialData {
  analysis: Analysis;
  sections: Section[];
}

const bpmText = (bpm: number) => bpm.toLocaleString("es-AR", { maximumFractionDigits: 1 });

/**
 * The result as it lands. The page is laid out from the start with dashes where values will go,
 * so nothing moves when the analysis arrives: values appear in place and the sections stamp in
 * one by one like marks on a chord sheet.
 */
export function ResultFill({ partial, complete }: { partial: PartialData | null; complete: boolean }) {
  const analysis = partial?.analysis ?? null;
  const key = analysis?.key ? keyLabel(analysis.key) : null;
  const grid = analysis?.grid ?? null;
  const runs = partial ? sectionRuns(partial.sections) : [];
  const chords = analysis ? chordsSummary(analysis.chords) : [];

  return (
    <section aria-labelledby="resultado-titulo" className={styles.block}>
      <h2 id="resultado-titulo" className={styles.heading}>
        {complete ? "Resultado" : analysis ? "Resultado parcial" : "Resultado"}
      </h2>
      <dl className={styles.facts} data-ready={analysis ? "" : undefined}>
        <div className={styles.fact}>
          <dt>Tonalidad</dt>
          <dd className={styles.value}>
            {key ? (
              <span className={styles.enter} title={key.tooltip ?? undefined}>
                <span className={`${styles.big} mono`}>{key.note}</span>{" "}
                <span className={styles.mode}>{key.mode}</span>
                {key.alternative && <span className={styles.alt}>o {key.alternative}</span>}
              </span>
            ) : (
              <Pending showDash={!analysis} />
            )}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt>Tempo</dt>
          <dd className={styles.value}>
            {grid ? (
              <span className={styles.enter} style={{ animationDelay: "90ms" }}>
                <span className={`${styles.big} mono`}>{bpmText(grid.bpm)}</span>{" "}
                <span className={styles.mode}>BPM</span>
              </span>
            ) : (
              <Pending showDash={!analysis} />
            )}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt>Compás</dt>
          <dd className={`${styles.value} mono`}>
            {grid ? (
              <span className={styles.enter} style={{ animationDelay: "180ms" }}>
                {grid.time_signature}
              </span>
            ) : (
              <Pending showDash={!analysis} />
            )}
          </dd>
        </div>
        <div className={styles.fact}>
          <dt>Duración</dt>
          <dd className={`${styles.value} mono`}>
            {analysis ? (
              <span className={styles.enter} style={{ animationDelay: "270ms" }}>
                {formatDuration(analysis.duration)}
              </span>
            ) : (
              <Pending showDash />
            )}
          </dd>
        </div>
      </dl>

      <div className={styles.group}>
        <h3 className={styles.label}>Secciones</h3>
        <ol className={styles.chips} aria-label="Secciones detectadas">
          {runs.map((run, index) => (
            <li
              key={`${run.label}-${index}`}
              className={`${styles.chip} ${styles.stamp}`}
              style={{ animationDelay: `${Math.min(index, 14) * 70 + 360}ms` }}
            >
              {run.label}
              {run.count > 1 && <span className={`${styles.times} mono`}> ×{run.count}</span>}
            </li>
          ))}
        </ol>
        {analysis && runs.length === 0 && (
          <p className={styles.empty}>No encontramos secciones. Podés marcarlas a mano en el estudio.</p>
        )}
        {!analysis && <p className={styles.empty}>Aparecen en cuanto termina el análisis.</p>}
      </div>

      {chords.length > 0 && (
        <div className={styles.group}>
          <h3 className={styles.label}>Acordes más presentes</h3>
          <p
            className={`${styles.chords} mono ${styles.enter}`}
            style={{ animationDelay: `${Math.min(runs.length, 14) * 70 + 480}ms` }}
          >
            {chords.join(" · ")}
          </p>
        </div>
      )}
    </section>
  );
}

function Pending({ showDash }: { showDash: boolean }) {
  return showDash ? (
    <span className={styles.dash} aria-hidden="true">
      —
    </span>
  ) : (
    <span className={styles.dash}>No disponible</span>
  );
}
