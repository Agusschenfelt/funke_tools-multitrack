import { describe, expect, it } from "vitest";
import { formatAgo, formatTimeLeft } from "./format";
import {
  MAX_SHOWN,
  RECENT_KEY,
  markGone,
  parseRecent,
  readRecent,
  recentHref,
  rememberSong,
  removeRecent,
  updateRecent,
  visibleRecent,
  type RecentStore,
} from "./recentSongs";

const HOUR = 3_600_000;
const NOW = 1_800_000_000_000;

function memoryStore(initial?: string): RecentStore & { raw: () => string | null } {
  let value: string | null = initial ?? null;
  return {
    getItem: () => value,
    setItem: (_key, next) => {
      value = next;
    },
    raw: () => value,
  };
}

const song = (id: string, ageHours = 1, extra: Record<string, unknown> = {}) => ({
  id,
  filename: `${id}.wav`,
  createdAt: NOW - ageHours * HOUR,
  expiresAt: NOW - ageHours * HOUR + 24 * HOUR,
  ...extra,
});

describe("rememberSong / readRecent", () => {
  it("stores a song and reads it back newest first", () => {
    const store = memoryStore();
    rememberSong(song("old", 5), NOW, store);
    rememberSong(song("new", 1), NOW, store);
    expect(readRecent(NOW, store).map((e) => e.id)).toEqual(["new", "old"]);
  });

  it("refreshes the same id without duplicating or losing known job ids", () => {
    const store = memoryStore();
    rememberSong({ ...song("a"), jobs: { analyze: "job-1", separate: null } }, NOW, store);
    rememberSong(song("a"), NOW, store);
    const [only, ...rest] = readRecent(NOW, store);
    expect(rest).toEqual([]);
    expect(only.jobs).toEqual({ analyze: "job-1", separate: null });
  });

  it("drops expired songs from the result and from storage", () => {
    const store = memoryStore();
    rememberSong(song("fresh", 1), NOW, store);
    rememberSong(song("stale", 30), NOW - 29 * HOUR, store);
    expect(readRecent(NOW, store).map((e) => e.id)).toEqual(["fresh"]);
    expect(parseRecent(store.raw()).map((e) => e.id)).toEqual(["fresh"]);
  });
});

describe("updateRecent / markGone / removeRecent", () => {
  it("merges job ids and status into one entry", () => {
    const store = memoryStore();
    rememberSong(song("a"), NOW, store);
    updateRecent("a", { jobs: { analyze: "j1" } }, NOW, store);
    updateRecent("a", { jobs: { separate: "j2" }, status: "ready" }, NOW, store);
    const [entry] = readRecent(NOW, store);
    expect(entry.jobs).toEqual({ analyze: "j1", separate: "j2" });
    expect(entry.status).toBe("ready");
  });

  it("ignores an unknown id", () => {
    const store = memoryStore();
    rememberSong(song("a"), NOW, store);
    updateRecent("zzz", { status: "ready" }, NOW, store);
    expect(readRecent(NOW, store)).toHaveLength(1);
  });

  it("hides a gone song but keeps it out of the list shown", () => {
    const store = memoryStore();
    rememberSong(song("a"), NOW, store);
    rememberSong(song("b", 2), NOW, store);
    const all = markGone("a", NOW, store);
    expect(visibleRecent(all, NOW).map((e) => e.id)).toEqual(["b"]);
  });

  it("removes only the chosen entry", () => {
    const store = memoryStore();
    rememberSong(song("a"), NOW, store);
    rememberSong(song("b", 2), NOW, store);
    expect(removeRecent("a", NOW, store).map((e) => e.id)).toEqual(["b"]);
    expect(readRecent(NOW, store).map((e) => e.id)).toEqual(["b"]);
  });
});

describe("visibleRecent", () => {
  it("caps the list at MAX_SHOWN", () => {
    const entries = Array.from({ length: 12 }, (_, i) => ({
      ...song(`s${i}`, i + 1),
      jobs: { analyze: null, separate: null },
      status: "pending" as const,
    }));
    expect(visibleRecent(entries, NOW)).toHaveLength(MAX_SHOWN);
  });
});

describe("corrupt or blocked storage", () => {
  it("reads an empty list from garbage text", () => {
    expect(readRecent(NOW, memoryStore("{not json"))).toEqual([]);
    expect(readRecent(NOW, memoryStore('{"a":1}'))).toEqual([]);
  });

  it("drops malformed entries and keeps the good ones", () => {
    const good = { ...song("ok"), jobs: { analyze: null, separate: null }, status: "pending" };
    const text = JSON.stringify([
      null,
      "x",
      { id: "../etc", filename: "a", createdAt: NOW, expiresAt: NOW + 1 },
      { id: "nofile", createdAt: NOW, expiresAt: NOW + HOUR },
      { id: "nan", filename: "a", createdAt: "x", expiresAt: NOW + HOUR },
      good,
    ]);
    expect(readRecent(NOW, memoryStore(text)).map((e) => e.id)).toEqual(["ok"]);
  });

  it("sanitizes job ids that could break a URL", () => {
    const text = JSON.stringify([{ ...song("a"), jobs: { analyze: "x&s=evil", separate: "ok-1" } }]);
    const [entry] = parseRecent(text);
    expect(entry.jobs).toEqual({ analyze: null, separate: "ok-1" });
  });

  it("does not throw when the store throws", () => {
    const broken: RecentStore = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("full");
      },
    };
    expect(readRecent(NOW, broken)).toEqual([]);
    expect(() => rememberSong(song("a"), NOW, broken)).not.toThrow();
    expect(() => removeRecent("a", NOW, broken)).not.toThrow();
  });

  it("works with no store at all", () => {
    expect(readRecent(NOW, null)).toEqual([]);
    expect(rememberSong(song("a"), NOW, null).map((e) => e.id)).toEqual(["a"]);
  });

  it("stores under a stable key", () => {
    const store = memoryStore();
    rememberSong(song("a"), NOW, store);
    expect(RECENT_KEY).toBe("multitrack:recent-songs");
    expect(store.raw()).toContain('"id":"a"');
  });
});

describe("recentHref", () => {
  const base = { ...song("abc"), jobs: { analyze: "ja", separate: "js" } };
  it("goes to the studio when ready", () => {
    expect(recentHref({ ...base, status: "ready" })).toBe("/temas/abc/estudio");
  });
  it("goes to processing with the known job ids", () => {
    expect(recentHref({ ...base, status: "pending" })).toBe("/temas/abc?a=ja&s=js");
    expect(recentHref({ ...base, jobs: { analyze: null, separate: null }, status: "pending" })).toBe(
      "/temas/abc",
    );
  });
});

describe("time wording", () => {
  it("says how long ago", () => {
    expect(formatAgo(10_000)).toBe("hace un momento");
    expect(formatAgo(5 * 60_000)).toBe("hace 5 min");
    expect(formatAgo(2 * HOUR + 1)).toBe("hace 2 h");
    expect(formatAgo(50 * HOUR)).toBe("hace 2 d");
    expect(formatAgo(-5)).toBe("hace un momento");
  });
  it("says how long is left", () => {
    expect(formatTimeLeft(30_000)).toBe("menos de 1 min");
    expect(formatTimeLeft(35 * 60_000)).toBe("35 min");
    expect(formatTimeLeft(2 * HOUR)).toBe("2 h");
    expect(formatTimeLeft(21 * HOUR + 40 * 60_000)).toBe("21 h 40 min");
  });
});
