import { API_URL, type ArtifactLink } from "@/lib/api";

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

export interface StemSource {
  name: StemName;
  url: string;
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
