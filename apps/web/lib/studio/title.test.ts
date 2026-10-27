import { describe, expect, it } from "vitest";
import { isGenericTitle, loadTitle, MAX_TITLE, sanitizeTitle, saveTitle, titleView, UNTITLED } from "./title";

describe("isGenericTitle", () => {
  it.each([
    "Untitled.mp3",
    "untitled",
    "Untitled 3.wav",
    "audio.mp3",
    "audio_001.wav",
    "Track 07.mp3",
    "track-2",
    "20260301.mp3",
    "123.m4a",
    "New Recording 12.m4a",
    "Nueva grabación (2).m4a",
    "WhatsApp Audio 2024-05-01.mp3",
    "Sin título.wav",
    "Mix 2",
    "",
  ])("%s is generic", (name) => {
    expect(isGenericTitle(name)).toBe(true);
  });

  it.each(["Wonderwall.mp3", "Audioslave - Like a Stone.mp3", "Mix de Fiesta Brava.wav", "Soy Rebelde.mp3", "Tracks of my tears.mp3"])(
    "%s is a real name",
    (name) => {
      expect(isGenericTitle(name)).toBe(false);
    },
  );
});

describe("titleView", () => {
  it("shows the fallback with the duration for a generic file name", () => {
    expect(titleView("Untitled.mp3", 225, null)).toEqual({
      text: UNTITLED,
      detail: "3:45",
      fallback: true,
      renamed: false,
    });
  });

  it("omits the duration when it is unknown", () => {
    expect(titleView("audio.wav", 0, null).detail).toBeNull();
  });

  it("keeps a real file name without its extension", () => {
    expect(titleView("Soy Rebelde.mp3", 200, null)).toEqual({
      text: "Soy Rebelde",
      detail: null,
      fallback: false,
      renamed: false,
    });
  });

  it("a local rename wins over both", () => {
    expect(titleView("Untitled.mp3", 200, "Zamba del ensayo").text).toBe("Zamba del ensayo");
    expect(titleView("Soy Rebelde.mp3", 200, "Mi versión").renamed).toBe(true);
  });
});

describe("sanitizeTitle", () => {
  it("trims, collapses whitespace and caps the length", () => {
    expect(sanitizeTitle("  Hola   mundo \n")).toBe("Hola mundo");
    expect(sanitizeTitle("x".repeat(200))?.length).toBe(MAX_TITLE);
  });
  it("returns null when nothing is left", () => {
    expect(sanitizeTitle("   ")).toBeNull();
  });
});

function fakeStore(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

describe("title storage", () => {
  it("round-trips per song", () => {
    const store = fakeStore();
    expect(saveTitle("a", "Mi tema", store)).toBe(true);
    expect(loadTitle("a", store)).toBe("Mi tema");
    expect(loadTitle("b", store)).toBeNull();
  });

  it("an empty rename forgets the entry", () => {
    const store = fakeStore();
    saveTitle("a", "Mi tema", store);
    saveTitle("a", "  ", store);
    expect(store.data.size).toBe(0);
  });

  it("survives a store that throws or does not exist", () => {
    const broken = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("denied");
      },
      removeItem: () => {
        throw new Error("denied");
      },
    };
    expect(loadTitle("a", broken)).toBeNull();
    expect(saveTitle("a", "x", broken)).toBe(false);
    expect(loadTitle("a", null)).toBeNull();
    expect(saveTitle("a", "x", null)).toBe(false);
  });
});
