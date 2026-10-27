import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import {
  SONG_TTL_MS,
  isGoneError,
  isSongReady,
  recentFromUpload,
  statusAfterLookup,
} from "./recentVerification";

const NOW = 1_800_000_000_000;
const upload = (created_at: string, expires_at: string) => ({
  id: "s1",
  filename: "a.wav",
  created_at,
  expires_at,
});
const artifacts = (analysis: boolean, stems: number) => ({
  artifacts: { analysis, stems: Array.from({ length: stems }) },
});

describe("recentFromUpload", () => {
  it("converts the API dates to epoch milliseconds", () => {
    const entry = recentFromUpload(
      upload("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"),
      NOW,
    );
    expect(entry).toEqual({
      id: "s1",
      filename: "a.wav",
      createdAt: Date.parse("2026-01-01T00:00:00Z"),
      expiresAt: Date.parse("2026-01-02T00:00:00Z"),
    });
  });

  it("falls back to now and now + 24 h when the dates do not parse", () => {
    const entry = recentFromUpload(upload("nope", ""), NOW);
    expect(entry.createdAt).toBe(NOW);
    expect(entry.expiresAt).toBe(NOW + SONG_TTL_MS);
  });

  it("keeps a valid creation date and derives only the expiry", () => {
    const created = Date.parse("2026-01-01T00:00:00Z");
    const entry = recentFromUpload(upload("2026-01-01T00:00:00Z", "garbage"), NOW);
    expect(entry.createdAt).toBe(created);
    expect(entry.expiresAt).toBe(created + SONG_TTL_MS);
  });
});

describe("lookup verdicts", () => {
  it("is ready only with analysis and at least one stem", () => {
    expect(isSongReady(artifacts(true, 6))).toBe(true);
    expect(isSongReady(artifacts(true, 0))).toBe(false);
    expect(isSongReady(artifacts(false, 6))).toBe(false);
  });

  it("proposes ready only when it is a change", () => {
    expect(statusAfterLookup(artifacts(true, 2), "pending")).toBe("ready");
    expect(statusAfterLookup(artifacts(true, 2), "ready")).toBeNull();
    expect(statusAfterLookup(artifacts(false, 0), "pending")).toBeNull();
  });

  it("treats only 404 and 410 as gone", () => {
    expect(isGoneError(new ApiError("http", 404))).toBe(true);
    expect(isGoneError(new ApiError("http", 410))).toBe(true);
    expect(isGoneError(new ApiError("http", 500))).toBe(false);
    expect(isGoneError(new ApiError("network", null))).toBe(false);
    expect(isGoneError(new Error("boom"))).toBe(false);
  });
});
