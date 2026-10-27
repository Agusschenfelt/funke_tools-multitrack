import { describe, expect, it } from "vitest";
import type { StemSource } from "@/lib/audio/stems";
import { DOWNLOADS_LABEL, MIX_DOWNLOAD_LABEL, PACK_LABEL, stemDownloads } from "./downloads";

const wavs: StemSource[] = [
  { name: "drums", url: "http://x/d.wav" },
  { name: "vocals", url: "http://x/v.wav" },
];

describe("stemDownloads", () => {
  it("lists one WAV per stem in the given order with readable names", () => {
    expect(stemDownloads(wavs, "Soy Rebelde")).toEqual([
      { id: "drums", label: "Batería", url: "http://x/d.wav", filename: "Soy Rebelde - Batería.wav" },
      { id: "vocals", label: "Voz", url: "http://x/v.wav", filename: "Soy Rebelde - Voz.wav" },
    ]);
  });

  it("strips characters a file name cannot hold", () => {
    expect(stemDownloads(wavs, 'A/B: "C"?')[0].filename).toBe("A B C - Batería.wav");
  });

  it("is empty for a song without lossless stems", () => {
    expect(stemDownloads([], "x")).toEqual([]);
  });
});

describe("labels", () => {
  it("keeps the two exports apart", () => {
    expect(MIX_DOWNLOAD_LABEL).toBe("Bajar esta mezcla (WAV)");
    expect(PACK_LABEL).toBe("Exportar pack");
    expect(DOWNLOADS_LABEL).not.toBe(PACK_LABEL);
  });
});
