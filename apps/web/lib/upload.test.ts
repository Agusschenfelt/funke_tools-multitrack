import { describe, expect, it } from "vitest";
import { formatBytes } from "./format";
import {
  ACCEPT,
  BROWSER_ESTIMATE_SLACK_SECONDS,
  MAX_DURATION_SECONDS,
  checkDuration,
  extensionOf,
  limitLabel,
  tooLongMessage,
  validateFile,
} from "./upload";

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

describe("checkDuration", () => {
  it("lets the server decide when the duration is unknown", () => {
    expect(checkDuration(null)).toEqual({ ok: true });
    expect(checkDuration(Number.NaN)).toEqual({ ok: true });
  });
  it("accepts up to the limit plus the browser's estimate slack", () => {
    expect(checkDuration(180)).toEqual({ ok: true });
    expect(checkDuration(MAX_DURATION_SECONDS)).toEqual({ ok: true });
    expect(checkDuration(MAX_DURATION_SECONDS + BROWSER_ESTIMATE_SLACK_SECONDS)).toEqual({ ok: true });
  });
  it("blocks a clearly longer song with the duration in the message", () => {
    const seconds = MAX_DURATION_SECONDS + BROWSER_ESTIMATE_SLACK_SECONDS + 1;
    expect(checkDuration(seconds)).toEqual({
      ok: false,
      code: "duration",
      message: "Este tema dura 10:03. El máximo es 10 minutos.",
    });
  });
  it("derives the limit text from the limit", () => {
    expect(checkDuration(200, 120)).toMatchObject({ message: "Este tema dura 3:20. El máximo es 2 minutos." });
    expect(limitLabel(60)).toBe("1 minuto");
    expect(limitLabel(90)).toBe("1:30 minutos");
  });
});

describe("tooLongMessage", () => {
  it("formats minutes and zero-padded seconds, past one hour too", () => {
    expect(tooLongMessage(1421.7)).toBe("Este tema dura 23:41. El máximo es 10 minutos.");
    expect(tooLongMessage(3605)).toBe("Este tema dura 60:05. El máximo es 10 minutos.");
  });
});
