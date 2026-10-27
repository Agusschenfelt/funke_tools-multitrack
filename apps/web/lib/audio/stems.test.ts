import { describe, expect, it } from "vitest";
import { orderStems, stemNameOf, studioSources } from "./stems";

const link = (name: string) => ({ name, url: `/files/${name}`, token_expires_at: "" });

describe("stems", () => {
  it("orders known stems for the lanes and makes URLs absolute", () => {
    const stems = orderStems([link("vocals.wav"), link("bass.wav"), link("drums.wav"), link("x.txt")]);
    expect(stems.map((s) => s.name)).toEqual(["drums", "bass", "vocals"]);
    expect(stems[0].url).toMatch(/^https?:\/\/.+\/files\/drums\.wav$/);
  });
  it("recognises stem file names only", () => {
    expect(stemNameOf("Guitar.WAV")).toBe("guitar");
    expect(stemNameOf("click.wav")).toBeNull();
  });

  describe("studioSources", () => {
    const wavs = [link("drums.wav"), link("bass.wav")];
    const previews = [link("bass.m4a"), link("drums.m4a")];
    const meta = { samples: 1000, sample_rate: 44100, priming_samples: 1024 };

    it("prefers previews, in lane order, with the alignment of the WAV stems", () => {
      const { sources, compressed } = studioSources({ stems: wavs, previews, preview: meta });
      expect(compressed).toBe(true);
      expect(sources.map((s) => s.name)).toEqual(["drums", "bass"]);
      expect(sources[0].url).toMatch(/drums\.m4a$/);
      expect(sources[0].alignment).toEqual({ samples: 1000, primingSamples: 1024, sampleRate: 44100 });
    });

    it("falls back to the WAV stems for older songs", () => {
      for (const artifacts of [
        { stems: wavs },
        { stems: wavs, previews: [], preview: null },
        { stems: wavs, previews, preview: null },
        { stems: wavs, previews: [link("drums.m4a")], preview: meta },
      ]) {
        const { sources, compressed } = studioSources(artifacts);
        expect(compressed).toBe(false);
        expect(sources.map((s) => s.url.split(".").pop())).toEqual(["wav", "wav"]);
        expect(sources.every((s) => s.alignment === undefined)).toBe(true);
      }
    });
  });
});
