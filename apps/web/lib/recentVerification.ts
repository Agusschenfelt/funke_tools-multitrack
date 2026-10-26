/**
 * Pure decisions behind the "recent songs" list, kept out of the components so they can be tested:
 * what to remember after an upload, and what the API's answer says about a remembered song.
 */
import { ApiError, type SongOut } from "@/lib/api";
import type { RecentSong, RecentStatus } from "@/lib/recentSongs";

/** Songs expire 24 h after upload (fixed in the API); used only when the API dates are unusable. */
export const SONG_TTL_MS = 24 * 3_600_000;

/**
 * The entry to remember for a freshly uploaded song. API dates that do not parse would become NaN
 * and be rejected on the next read, losing the song from the list, so they fall back to "now" and
 * "now + 24 h".
 */
export function recentFromUpload(
  song: Pick<SongOut, "id" | "filename" | "created_at" | "expires_at">,
  nowMs: number,
): Pick<RecentSong, "id" | "filename" | "createdAt" | "expiresAt"> {
  const created = Date.parse(song.created_at);
  const expires = Date.parse(song.expires_at);
  const createdAt = Number.isFinite(created) ? created : nowMs;
  const expiresAt = Number.isFinite(expires) ? expires : createdAt + SONG_TTL_MS;
  return { id: song.id, filename: song.filename, createdAt, expiresAt };
}

/** A song is ready for the studio once its analysis and at least one stem exist. */
export function isSongReady(song: { artifacts: { analysis: boolean; stems: unknown[] } }): boolean {
  return song.artifacts.analysis && song.artifacts.stems.length > 0;
}

/** The status change a successful lookup implies, or null when the entry stays as it is. */
export function statusAfterLookup(
  song: { artifacts: { analysis: boolean; stems: unknown[] } },
  current: RecentStatus,
): RecentStatus | null {
  return isSongReady(song) && current !== "ready" ? "ready" : null;
}

/** Only a definite 404/410 proves the song is gone; any other failure says nothing about it. */
export function isGoneError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.kind === "http" &&
    (error.status === 404 || error.status === 410)
  );
}
