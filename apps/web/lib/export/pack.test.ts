import { describe, expect, it } from "vitest";
import type { StemName } from "@/lib/audio/stems";
import { fileStem, keyLabel, packFiles, roundHalfEven, sanitizeFilename, wavNames, zipName } from "./pack";

const SIX: StemName[] = ["drums", "bass", "piano", "guitar", "other", "vocals"];
const FOUR: StemName[] = ["drums", "bass", "other", "vocals"];

describe("wavNames", () => {
  it("playback, six stems, no vocals: English names, Split Track last", () => {
    expect(wavNames("playback", SIX, false)).toEqual([
      "Click",
      "Guide",
      "Drums",
      "Bass",
      "Keys",
      "Electric Guitar",
      "Tracks",
      "Split Track",
    ]);
  });

  it("daw, six stems with vocals: numbered Spanish names", () => {
    expect(wavNames("daw", SIX, true)).toEqual([
      "01 Click",
      "02 Guía",
      "03 Batería",
      "04 Bajo",
      "05 Teclados",
      "06 Guitarra eléctrica",
      "07 Pistas",
      "08 Voz",
      "09 Split Track",
    ]);
  });

  it("four stems skip the ones the song does not have", () => {
    expect(wavNames("playback", FOUR, true)).toEqual([
      "Click",
      "Guide",
      "Drums",
      "Bass",
      "Tracks",
      "Vocals",
      "Split Track",
    ]);
    expect(wavNames("daw", FOUR, false)).toEqual([
      "01 Click",
      "02 Guía",
      "03 Batería",
      "04 Bajo",
      "05 Pistas",
      "06 Split Track",
    ]);
  });

  it("leaves vocals out unless asked, and ignores stem order in the input", () => {
    expect(wavNames("playback", [...SIX].reverse(), false)).not.toContain("Vocals");
    expect(wavNames("playback", [...SIX].reverse(), true).slice(2, 4)).toEqual(["Drums", "Bass"]);
  });
});

describe("packFiles", () => {
  it("adds the text files after the WAVs, with .wav extensions", () => {
    const names = packFiles("daw", FOUR, false).map((f) => f.name);
    expect(names).toEqual([
      "01 Click.wav",
      "02 Guía.wav",
      "03 Batería.wav",
      "04 Bajo.wav",
      "05 Pistas.wav",
      "06 Split Track.wav",
      "Secciones.txt",
      "Tempo.mid",
      "Cómo importar.txt",
      "stagepack.json",
    ]);
  });

  it("gives every file a note", () => {
    expect(packFiles("playback", SIX, true).every((f) => f.note.length > 0)).toBe(true);
  });
});

describe("zipName", () => {
  it("is <Título> - <Tono> - <BPM> BPM.zip", () => {
    expect(zipName("Mi Canción.mp3", { key: "A", mode: "major" }, 120)).toBe("Mi Canción - A - 120 BPM.zip");
    expect(zipName("t.wav", { key: "E", mode: "minor" }, 97.4)).toBe("t - Em - 97 BPM.zip");
  });

  it("drops the key when unknown", () => {
    expect(zipName("t.wav", null, 90)).toBe("t - 90 BPM.zip");
    expect(zipName("t.wav", { key: "unknown", mode: "major" }, 90)).toBe("t - 90 BPM.zip");
    expect(zipName("t.wav", { key: "C", mode: "other" }, 90)).toBe("t - 90 BPM.zip");
  });

  it("rounds halves to even like Python", () => {
    expect(roundHalfEven(120.5)).toBe(120);
    expect(roundHalfEven(121.5)).toBe(122);
    expect(roundHalfEven(99.4)).toBe(99);
    expect(zipName("t.wav", null, 120.5)).toBe("t - 120 BPM.zip");
  });

  it("cleans unsafe characters and falls back to Stage Pack", () => {
    expect(sanitizeFilename('a/b:c*"d')).toBe("a b c d");
    expect(sanitizeFilename("  ..x..  ")).toBe("x");
    expect(zipName("???.wav", null, 100)).toBe("Stage Pack - 100 BPM.zip");
  });
});

describe("fileStem and keyLabel", () => {
  it("strips only the last suffix, like Path.stem", () => {
    expect(fileStem("a.b.mp3")).toBe("a.b");
    expect(fileStem(".hidden")).toBe(".hidden");
    expect(fileStem("noext")).toBe("noext");
  });

  it("labels minor keys with m", () => {
    expect(keyLabel({ key: "F#", mode: "minor" })).toBe("F#m");
    expect(keyLabel({ key: "F#", mode: "major" })).toBe("F#");
    expect(keyLabel(undefined)).toBeNull();
  });
});
