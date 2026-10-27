import { API_URL, type ArtifactLink, type Artifacts } from "@/lib/api";

/** Lane order: rhythm section first, voice last. */
export const STEM_ORDER = ["drums", "bass", "piano", "guitar", "other", "vocals"] as const;
export type StemName = (typeof STEM_ORDER)[number];

export const STEM_LABEL: Record<StemName, string> = {
  drums: "Batería",
  bass: "Bajo",
  piano: "Teclados",
  guitar: "Guitarra",
  other: "Otros",
  vocals: "Voz",
};

/** What a compressed preview needs to line up with the WAV stem it stands for. */
export interface PreviewAlignment {
  /** Exact sample count of the WAV stems. */
  samples: number;
  /** Encoder delay at the start of the preview when the decoder does not hide it. */
  primingSamples: number;
}

export interface StemSource {
  name: StemName;
  url: string;
  /** Set for compressed previews; absent for the lossless WAV stems. */
  alignment?: PreviewAlignment;
}

/** `drums.wav` -> `drums`; null for anything that is not one of the six stems. */
export function stemNameOf(file: string): StemName | null {
  const base = file.replace(/\.[a-z0-9]+$/i, "").toLowerCase();
  return (STEM_ORDER as readonly string[]).includes(base) ? (base as StemName) : null;
}

/** Signed links come relative to the API (`/files/<token>`). */
export function absoluteUrl(url: string): string {
  return /^https?:\/\//i.test(url) ? url : `${API_URL}${url}`;
}

/** Known stems from the song's links, in lane order. */
export function orderStems(links: readonly ArtifactLink[]): StemSource[] {
  const found = new Map<StemName, string>();
  for (const link of links) {
    const name = stemNameOf(link.name);
    if (name) found.set(name, absoluteUrl(link.url));
  }
  return STEM_ORDER.filter((name) => found.has(name)).map((name) => ({
    name,
    url: found.get(name) as string,
  }));
}

export interface StudioSources {
  sources: StemSource[];
  /** True when the sources are the compressed previews. */
  compressed: boolean;
}

/**
 * The files the studio downloads: the compressed previews when the song has one for every stem
 * and says how they line up, the WAV stems otherwise (songs separated before previews existed).
 */
export function studioSources(
  artifacts: Pick<Artifacts, "stems" | "previews" | "preview">,
): StudioSources {
  const wavs = orderStems(artifacts.stems);
  const meta = artifacts.preview;
  if (meta && artifacts.previews?.length) {
    const previews = new Map(orderStems(artifacts.previews).map((s) => [s.name, s.url]));
    if (wavs.length > 0 && wavs.every((s) => previews.has(s.name))) {
      const alignment = { samples: meta.samples, primingSamples: meta.priming_samples };
      return {
        sources: wavs.map((s) => ({ name: s.name, url: previews.get(s.name) as string, alignment })),
        compressed: true,
      };
    }
  }
  return { sources: wavs, compressed: false };
}
