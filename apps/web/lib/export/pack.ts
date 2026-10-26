/**
 * What the Stage Pack ZIP will contain, computed in the browser for the preview.
 *
 * KEEP IN SYNC with the server: `packages/audio-core/audio_core/stagepack.py`
 * (`STEM_NAMES`, `destination_names`, `zip_name`, `key_label`, `sanitize_filename`). If those
 * change, this module and its tests must change with them.
 */
import type { Destination } from "./options";
import type { StemName } from "@/lib/audio/stems";

/** Stem -> [playback name, DAW name], in pack order (same order as the server's STEM_NAMES). */
const STEM_FILE: Record<StemName, readonly [string, string]> = {
  drums: ["Drums", "Batería"],
  bass: ["Bass", "Bajo"],
  piano: ["Keys", "Teclados"],
  guitar: ["Electric Guitar", "Guitarra eléctrica"],
  other: ["Tracks", "Pistas"],
  vocals: ["Vocals", "Voz"],
};
const PACK_ORDER: readonly StemName[] = ["drums", "bass", "piano", "guitar", "other", "vocals"];

export interface PackFile {
  name: string;
  /** Short plain-Spanish note on what the file is. */
  note: string;
}

/** WAV base names in pack order. DAW names are numbered `01 Click`, `02 Guía`, ... */
export function wavNames(
  destination: Destination,
  stems: readonly StemName[],
  includeVocals: boolean,
): string[] {
  const i = destination === "playback" ? 0 : 1;
  const present = PACK_ORDER.filter((s) => stems.includes(s) && (s !== "vocals" || includeVocals));
  const bases = ["Click", i === 0 ? "Guide" : "Guía", ...present.map((s) => STEM_FILE[s][i]), "Split Track"];
  return destination === "daw"
    ? bases.map((base, n) => `${String(n + 1).padStart(2, "0")} ${base}`)
    : bases;
}

function noteFor(base: string, stems: readonly StemName[]): string {
  const bare = base.replace(/^\d+ /, "");
  if (bare === "Click") return "Click en la grilla de la canción";
  if (bare === "Guide" || bare === "Guía") return "Voz que canta las secciones";
  if (bare === "Split Track") return "Click y guía a la izquierda, banda a la derecha";
  const stem = PACK_ORDER.find((s) => STEM_FILE[s].includes(bare));
  return stem && stems.includes(stem) ? "Pista separada" : "Pista";
}

export function packFiles(
  destination: Destination,
  stems: readonly StemName[],
  includeVocals: boolean,
): PackFile[] {
  const wavs = wavNames(destination, stems, includeVocals).map((base) => ({
    name: `${base}.wav`,
    note: noteFor(base, stems),
  }));
  return [
    ...wavs,
    { name: "Secciones.txt", note: "Cada sección con su compás y su tiempo" },
    { name: "Tempo.mid", note: "Mapa de tempo y marcadores de sección" },
    { name: "Cómo importar.txt", note: "Pasos para importar en el destino elegido" },
    { name: "stagepack.json", note: "Informe técnico de cómo se armó el pack" },
  ];
}

/* ------------------------------------------------------------- ZIP name */

/** Server `sanitize_filename`: unsafe characters become spaces, runs collapse, max 120 chars. */
export function sanitizeFilename(text: string): string {
  // eslint-disable-next-line no-control-regex
  const cleaned = text.replace(/[<>:"/\\|?*\x00-\x1f]/g, " ").replace(/\s+/g, " ");
  return trimDotsSpaces(trimDotsSpaces(cleaned).slice(0, 120));
}

function trimDotsSpaces(text: string): string {
  return text.replace(/^[ .]+|[ .]+$/g, "");
}

/** Python `Path(name).stem`: the name without its last suffix (a leading dot is not a suffix). */
export function fileStem(filename: string): string {
  const base = filename.split(/[\\/]/).pop() ?? filename;
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

/** "G" for major, "Em" for minor, null when the key is unknown. */
export function keyLabel(key: { key: string; mode: string } | null | undefined): string | null {
  if (!key || (key.mode !== "major" && key.mode !== "minor")) return null;
  if (!key.key || key.key === "unknown") return null;
  return key.key + (key.mode === "minor" ? "m" : "");
}

/** Python `round()`: halves go to the even neighbour (120.5 -> 120, 121.5 -> 122). */
export function roundHalfEven(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (diff < 0.5) return floor;
  if (diff > 0.5) return floor + 1;
  return floor % 2 === 0 ? floor : floor + 1;
}

/** `<Título> - <Tono> - <BPM> BPM.zip`; the key part is left out when it is unknown. */
export function zipName(
  filename: string,
  key: { key: string; mode: string } | null | undefined,
  bpm: number,
): string {
  const parts = [sanitizeFilename(fileStem(filename)) || "Stage Pack"];
  const label = keyLabel(key);
  if (label) parts.push(sanitizeFilename(label));
  parts.push(`${roundHalfEven(bpm)} BPM`);
  return `${parts.join(" - ")}.zip`;
}
