/**
 * Starts the analyze and separate jobs for a song, keeping whichever one is already running.
 * A retry after a partial failure therefore enqueues only the missing job instead of duplicating
 * the one that started.
 */
import type { JobCreated } from "@/lib/api";
import type { TrackedJobs } from "@/lib/processing";

export interface JobStarters {
  analyze: () => Promise<JobCreated>;
  separate: () => Promise<JobCreated>;
}

export interface StartResult {
  /** Every id known so far, including ones carried over from an earlier attempt. */
  tracked: TrackedJobs;
  /** The first failure, or null when both jobs are running. */
  error: unknown;
}

export async function startMissingJobs(have: TrackedJobs, starters: JobStarters): Promise<StartResult> {
  const [analyze, separate] = await Promise.allSettled([
    have.analyze ? Promise.resolve<JobCreated | null>(null) : starters.analyze(),
    have.separate ? Promise.resolve<JobCreated | null>(null) : starters.separate(),
  ]);
  const tracked: TrackedJobs = {
    analyze: have.analyze ?? (analyze.status === "fulfilled" ? (analyze.value?.job_id ?? null) : null),
    separate:
      have.separate ?? (separate.status === "fulfilled" ? (separate.value?.job_id ?? null) : null),
  };
  const failed = [analyze, separate].find((r) => r.status === "rejected");
  return { tracked, error: failed ? (failed as PromiseRejectedResult).reason : null };
}

/** Query string the processing route reads; only ids that exist are carried. */
export function processingQuery(tracked: TrackedJobs): string {
  const params = new URLSearchParams();
  if (tracked.analyze) params.set("a", tracked.analyze);
  if (tracked.separate) params.set("s", tracked.separate);
  return params.toString();
}
