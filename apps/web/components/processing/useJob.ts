"use client";

import { useEffect, useState } from "react";
import { ApiError, getJob, type JobOut } from "@/lib/api";
import { isTerminal, nextPollDelay } from "@/lib/processing";

export interface JobPoll {
  job: JobOut | null;
  /** The API no longer knows this job (404): it expired or never existed. */
  lost: boolean;
  /** The last poll failed on the network; polling keeps going. */
  offline: boolean;
}

const EMPTY: JobPoll = { job: null, lost: false, offline: false };

/**
 * Polls GET /jobs/{id} with backoff that resets whenever the stage changes. Pauses while the tab
 * is hidden, stops at a terminal state, and aborts on unmount or when the id changes.
 */
export function useJob(jobId: string | null): JobPoll {
  const [state, setState] = useState<JobPoll & { jobId: string | null }>({ ...EMPTY, jobId: null });

  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inflight = false;
    let stopped = false;
    let attempt = 0;
    let lastKey = "";

    const tick = async () => {
      if (stopped || inflight || document.hidden) return;
      inflight = true;
      let delay = true;
      try {
        const job = await getJob(jobId, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setState({ jobId, job, lost: false, offline: false });
        if (isTerminal(job.status)) {
          stopped = true;
          delay = false;
        } else {
          const key = `${job.status}/${job.stage}`;
          attempt = key === lastKey ? attempt + 1 : 0;
          lastKey = key;
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.kind === "http" && error.status === 404) {
          setState({ jobId, job: null, lost: true, offline: false });
          stopped = true;
          delay = false;
        } else {
          attempt += 1;
          setState((prev) => ({ ...prev, jobId, offline: true }));
        }
      } finally {
        inflight = false;
      }
      if (delay && !stopped) timer = setTimeout(() => void tick(), nextPollDelay(attempt));
    };

    const onVisibility = () => {
      if (document.hidden) return;
      clearTimeout(timer);
      void tick();
    };

    document.addEventListener("visibilitychange", onVisibility);
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller.abort();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [jobId]);

  return state.jobId === jobId ? state : EMPTY;
}
