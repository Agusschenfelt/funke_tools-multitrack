import { describe, expect, it } from "vitest";
import { formatBytes } from "./format";
import { ACCEPT, extensionOf, validateFile } from "./upload";

const MB = 1024 * 1024;

describe("extensionOf", () => {
  it("lowercases and takes the last suffix", () => {
    expect(extensionOf("Mi Tema.FINAL.WAV")).toBe(".wav");
  });
  it("treats a leading dot alone and a missing dot as no extension", () => {
    expect(extensionOf(".wav")).toBe("");
    expect(extensionOf("cancion")).toBe("");
  });
  it("ignores directories in the name", () => {
    expect(extensionOf("C:\\musica\\tema.mp3")).toBe(".mp3");
  });
});

describe("validateFile", () => {
  it("accepts every allowed extension, in any case", () => {
    for (const ext of ACCEPT.split(",")) {
      expect(validateFile({ name: `tema${ext.toUpperCase()}`, size: MB })).toEqual({ ok: true });
    }
  });

  it("rejects an unsupported extension with the formats list", () => {
    const result = validateFile({ name: "tema.pdf", size: MB });
    expect(result).toMatchObject({ ok: false, code: "extension" });
    if (!result.ok) expect(result.message).toContain("WAV");
  });

  it("rejects a file with no extension", () => {
    expect(validateFile({ name: "tema", size: MB })).toMatchObject({ code: "extension" });
  });

  it("rejects an empty file", () => {
    expect(validateFile({ name: "tema.wav", size: 0 })).toMatchObject({ code: "empty" });
  });

  it("accepts exactly the limit and rejects one byte over, like the API", () => {
    expect(validateFile({ name: "a.wav", size: 100 * MB }, 100)).toEqual({ ok: true });
    const over = validateFile({ name: "a.wav", size: 100 * MB + 1 }, 100);
    expect(over).toMatchObject({ ok: false, code: "size" });
    if (!over.ok) expect(over.message).toContain("100 MB");
  });
});

describe("formatBytes", () => {
  it("uses es-AR decimals and binary units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1,5 KB");
    expect(formatBytes(12.4 * MB)).toBe("12,4 MB");
  });
});
