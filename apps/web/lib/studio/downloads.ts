/** What the "Descargas" panel offers: each stem as a WAV, and the browser-rendered mix. */
import { STEM_LABEL, type StemSource } from "@/lib/audio/stems";

export const DOWNLOADS_LABEL = "Descargas";
export const MIX_DOWNLOAD_LABEL = "Bajar esta mezcla (WAV)";
export const PACK_LABEL = "Exportar pack";

export interface StemDownload {
  id: string;
  label: string;
  url: string;
  filename: string;
}

/** A file name the browser will accept: no path separators or control characters. */
function safeName(title: string): string {
  const clean = title
    .replace(/[\u0000-\u001f<>:"/\\|?*]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[\s.]+|[\s.]+$/g, "");
  return clean || "Mi tema";
}

/**
 * One entry per lossless stem, in lane order. The API serves stems one by one and offers no
 * ZIP of them (the ZIP is the Stage Pack), so none is listed here.
 */
export function stemDownloads(wavs: readonly StemSource[], title: string): StemDownload[] {
  const base = safeName(title);
  return wavs.map(({ name, url }) => ({
    id: name,
    label: STEM_LABEL[name],
    url,
    filename: `${base} - ${STEM_LABEL[name]}.wav`,
  }));
}
