"use client";

import { useState, type ReactNode } from "react";
import { playClickPreview } from "@/lib/audio/preview";
import type { ClickSound, Destination, ExportOptions } from "@/lib/export/options";
import styles from "./ExportView.module.css";

interface Choice<T> {
  value: T;
  label: string;
  disabled?: boolean;
  note?: string;
}

function Radios<T extends string | number>({
  name,
  value,
  choices,
  onChange,
  describedBy,
  extra,
  segmented,
}: {
  name: string;
  value: T;
  choices: Choice<T>[];
  onChange: (value: T) => void;
  describedBy: string;
  extra?: (choice: Choice<T>) => ReactNode;
  /** Two short options read best side by side as one segmented control. */
  segmented?: boolean;
}) {
  return (
    <div className={segmented ? `${styles.choices} ${styles.segmented}` : styles.choices}>
      {choices.map((choice) => (
        <div key={String(choice.value)} className={styles.choiceRow}>
          <label className={styles.choice} data-disabled={choice.disabled || undefined}>
            <input
              type="radio"
              name={name}
              value={String(choice.value)}
              checked={value === choice.value}
              disabled={choice.disabled}
              aria-describedby={describedBy}
              onChange={() => onChange(choice.value)}
            />
            <span className={styles.choiceBox}>
              <span className={styles.choiceLabel}>{choice.label}</span>
              {choice.note && <span className={styles.choiceNote}>{choice.note}</span>}
            </span>
          </label>
          {extra?.(choice)}
        </div>
      ))}
    </div>
  );
}

function Group({
  id,
  legend,
  hint,
  children,
}: {
  id: string;
  legend: string;
  hint: string;
  children: ReactNode;
}) {
  return (
    <fieldset className={styles.group}>
      <legend className={styles.legend}>{legend}</legend>
      <p id={id} className={styles.hint}>
        {hint}
      </p>
      {children}
    </fieldset>
  );
}

function Switch({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className={styles.group}>
      <label className={styles.switch}>
        <input
          type="checkbox"
          role="switch"
          checked={checked}
          aria-describedby={id}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className={styles.track} aria-hidden="true" />
        <span className={styles.legend}>{label}</span>
      </label>
      <p id={id} className={styles.hint}>
        {hint}
      </p>
    </div>
  );
}

export function OptionsForm({
  options,
  disabled,
  onChange,
}: {
  options: ExportOptions;
  disabled: boolean;
  onChange: (patch: Partial<ExportOptions>) => void;
}) {
  const [previewNote, setPreviewNote] = useState("");
  const listen = async (sound: ClickSound) => {
    const ok = await playClickPreview(sound);
    setPreviewNote(ok ? "" : "Este navegador no pudo reproducir el sonido.");
  };

  return (
    <fieldset className={styles.options} disabled={disabled}>
      <legend className="visually-hidden">Opciones del pack</legend>

      <Group id="h-destination" legend="Destino" hint="Cómo se llaman los archivos y qué notas de importación trae.">
        <Radios<Destination | "prime">
          name="destination"
          value={options.destination}
          describedBy="h-destination"
          onChange={(destination) => {
            if (destination !== "prime") onChange({ destination });
          }}
          choices={[
            { value: "playback", label: "Playback", note: "MultiTracks.com" },
            { value: "daw", label: "DAW", note: "Ableton, Logic, Reaper…" },
            {
              value: "prime",
              label: "Prime",
              note: "próximamente: falta probarlo con una importación real",
              disabled: true,
            },
          ]}
        />
      </Group>

      <Group id="h-count" legend="Cuenta previa" hint="Compases de click antes de que empiece la canción.">
        <Radios
          name="count"
          segmented
          value={options.countInBars}
          describedBy="h-count"
          onChange={(countInBars) => onChange({ countInBars })}
          choices={[
            { value: 1, label: "1 compás" },
            { value: 2, label: "2 compases" },
          ]}
        />
      </Group>

      <Group id="h-click" legend="Sonido del click" hint="El primer tiempo de cada compás suena más agudo.">
        <Radios
          name="click"
          value={options.clickSound}
          describedBy="h-click"
          onChange={(clickSound) => onChange({ clickSound })}
          choices={[
            { value: "classic", label: "Clásico" },
            { value: "cowbell", label: "Cencerro" },
            { value: "woodblock", label: "Woodblock" },
            { value: "rimshot", label: "Rimshot" },
          ]}
          extra={(choice) => (
            <button
              type="button"
              className={styles.listen}
              onClick={() => void listen(choice.value)}
              aria-label={`Escuchar ${choice.label}`}
            >
              Escuchar
            </button>
          )}
        />
        <p className={styles.hint} role="status">
          {previewNote || "La vista previa es aproximada; el sonido final lo genera el servidor."}
        </p>
      </Group>

      <Group id="h-sub" legend="Subdivisión" hint="Negras: un click por tiempo. Corcheas: se suma un click suave entre tiempos.">
        <Radios
          name="sub"
          segmented
          value={options.subdivision}
          describedBy="h-sub"
          onChange={(subdivision) => onChange({ subdivision })}
          choices={[
            { value: "quarter", label: "Negras" },
            { value: "eighth", label: "Corcheas" },
          ]}
        />
      </Group>

      <Switch
        id="h-grid"
        label="Grilla recta"
        hint="Cuantiza el click al BPM promedio. Útil si el tema tiene un tempo estable; si no, dejalo apagado y el click sigue los tiempos detectados."
        checked={options.straightGrid}
        onChange={(straightGrid) => onChange({ straightGrid })}
      />

      <Switch
        id="h-extend"
        label="Extender la grilla a la intro"
        hint="Útil si la intro sigue el mismo tempo pero sin batería. Desactivalo si la intro es libre."
        checked={options.extendGrid}
        onChange={(extendGrid) => onChange({ extendGrid })}
      />

      <Group id="h-rate" legend="Frecuencia" hint="Los WAV salen a 24 bits. Usá la frecuencia de tu proyecto.">
        <Radios
          name="rate"
          segmented
          value={options.sampleRate}
          describedBy="h-rate"
          onChange={(sampleRate) => onChange({ sampleRate })}
          choices={[
            { value: 44100, label: "44,1 kHz" },
            { value: 48000, label: "48 kHz" },
          ]}
        />
      </Group>

      <Switch
        id="h-vocals"
        label="Incluir voz principal"
        hint="Apagado por defecto: el pack trae la banda sin la voz, para que cante quien toca."
        checked={options.includeVocals}
        onChange={(includeVocals) => onChange({ includeVocals })}
      />

      <Group id="h-lang" legend="Idioma de las cues" hint="La voz de la guía que anuncia las secciones, y el idioma de las notas de importación.">
        <Radios
          name="lang"
          segmented
          value={options.language}
          describedBy="h-lang"
          onChange={(language) => onChange({ language })}
          choices={[
            { value: "es", label: "Español" },
            { value: "en", label: "Inglés" },
          ]}
        />
      </Group>
    </fieldset>
  );
}
