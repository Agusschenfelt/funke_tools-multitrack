/**
 * Keeps retries of the same row from overwriting each other. Each retry takes a ticket for its
 * row; only the holder of the newest ticket may apply its result. The tracked ids live in a
 * single object that is merged key by key, so finishing one row never reverts the other.
 */
import type { RowKind, TrackedJobs } from "@/lib/processing";

export interface RetryGate {
  begin: (kind: RowKind) => number;
  isCurrent: (kind: RowKind, ticket: number) => boolean;
}

export function createRetryGate(): RetryGate {
  const latest: Record<RowKind, number> = { analyze: 0, separate: 0 };
  return {
    begin: (kind) => ++latest[kind],
    isCurrent: (kind, ticket) => latest[kind] === ticket,
  };
}

/** Returns `tracked` with one id replaced; the other id is untouched. */
export function withJob(tracked: TrackedJobs, kind: RowKind, jobId: string): TrackedJobs {
  return { ...tracked, [kind]: jobId };
}
