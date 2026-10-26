import { describe, expect, it, vi } from "vitest";
import { processingQuery, startMissingJobs } from "./startJobs";

const ok = (id: string) => vi.fn(async () => ({ job_id: id }));
const fail = () => vi.fn(async () => Promise.reject(new Error("boom")));

describe("startMissingJobs", () => {
  it("starts both when none exist", async () => {
    const r = await startMissingJobs({ analyze: null, separate: null }, { analyze: ok("a1"), separate: ok("s1") });
    expect(r).toEqual({ tracked: { analyze: "a1", separate: "s1" }, error: null });
  });

  it("keeps the started job when the other fails to enqueue", async () => {
    const r = await startMissingJobs({ analyze: null, separate: null }, { analyze: ok("a1"), separate: fail() });
    expect(r.tracked).toEqual({ analyze: "a1", separate: null });
    expect(r.error).toBeInstanceOf(Error);
  });

  it("retries only the missing job and carries both ids", async () => {
    const analyze = ok("a2");
    const separate = ok("s2");
    const r = await startMissingJobs({ analyze: "a1", separate: null }, { analyze, separate });
    expect(analyze).not.toHaveBeenCalled();
    expect(separate).toHaveBeenCalledOnce();
    expect(r).toEqual({ tracked: { analyze: "a1", separate: "s2" }, error: null });
    expect(processingQuery(r.tracked)).toBe("a=a1&s=s2");
  });

  it("works in the other direction", async () => {
    const r = await startMissingJobs({ analyze: null, separate: "s1" }, { analyze: ok("a2"), separate: fail() });
    expect(r.tracked).toEqual({ analyze: "a2", separate: "s1" });
    expect(r.error).toBeNull();
  });

  it("reports an error and keeps state when the retry fails again", async () => {
    const r = await startMissingJobs({ analyze: "a1", separate: null }, { analyze: ok("x"), separate: fail() });
    expect(r.tracked).toEqual({ analyze: "a1", separate: null });
    expect(r.error).toBeInstanceOf(Error);
  });
});

describe("processingQuery", () => {
  it("omits missing ids", () => {
    expect(processingQuery({ analyze: "a1", separate: null })).toBe("a=a1");
    expect(processingQuery({ analyze: null, separate: null })).toBe("");
  });
});
