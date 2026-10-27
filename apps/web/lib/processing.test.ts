import { describe, expect, it } from "vitest";
import type { JobOut } from "@/lib/api";
import {
  elapsedSeconds,
  failureMessage,
  formatElapsed,
  isTerminal,
  nextPollDelay,
  resolveTracked,
  rowView,
  sectionsSummary,
  stageLabel,
  statusLabel,
} from "@/lib/processing";

function job(over: Partial<JobOut> = {}): JobOut {
  return {
    job_id: "j",
    song_id: "s",
    kind: "analyze",
    status: "running",
    stage: "sections",
    error: null,
    created_at: "2026-10-26T10:00:00Z",
    started_at: "2026-10-26T10:00:05Z",
    finished_at: null,
    result: null,
    download_url: null,
    ...over,
  };
}

describe("nextPollDelay", () => {
  it("starts at 1.5 s, grows and caps at 5 s", () => {
    expect(nextPollDelay(0)).toBe(1500);
    expect(nextPollDelay(1)).toBeGreaterThan(1500);
    expect(nextPollDelay(2)).toBeGreaterThan(nextPollDelay(1));
    expect(nextPollDelay(50)).toBe(5000);
  });
  it("tolerates negative or fractional attempts", () => {
    expect(nextPollDelay(-3)).toBe(1500);
    expect(nextPollDelay(0.9)).toBe(1500);
  });
});

describe("status and stage mapping", () => {
  it("translates every known stage and hides unknown ones", () => {
    expect(stageLabel("decoding")).toBe("Leyendo audio");
    expect(stageLabel("separating")).toBe("Separando pistas");
    expect(stageLabel("previews")).toBe("Comprimiendo vista previa");
    expect(stageLabel("done")).toBe("Listo");
    expect(stageLabel("whatever")).toBe("—");
    expect(stageLabel(null)).toBe("—");
  });
  it("translates statuses and knows terminal ones", () => {
    expect(statusLabel("queued")).toBe("En cola");
    expect(statusLabel("failed")).toBe("Falló");
    expect(isTerminal("finished")).toBe(true);
    expect(isTerminal("failed")).toBe(true);
    expect(isTerminal("queued")).toBe(false);
    expect(isTerminal("running")).toBe(false);
  });
  it("maps failures to plain Spanish", () => {
    expect(failureMessage("separate", "torch.OutOfMemoryError: out of memory")).toMatch(/memoria/);
    expect(failureMessage("analyze", "ffmpeg: Invalid data found")).toMatch(/leer el audio/);
    expect(
      failureMessage("analyze", "worker_cpu.jobs.JobError: El tema dura 23:41 y el máximo es 10:00."),
    ).toBe("El tema dura 23:41 y el máximo es 10:00.");
    expect(failureMessage("analyze", null)).toBe("El análisis falló.");
    expect(failureMessage("separate", "boom")).toBe("La separación falló.");
  });
});

describe("elapsed time", () => {
  const now = Date.parse("2026-10-26T10:01:05Z");
  it("counts from start while running", () => {
    expect(elapsedSeconds(job(), now)).toBe(60);
  });
  it("counts from creation while queued", () => {
    expect(elapsedSeconds(job({ status: "queued", started_at: null }), now)).toBe(65);
  });
  it("freezes at the finish time", () => {
    const done = job({ status: "finished", finished_at: "2026-10-26T10:00:35Z" });
    expect(elapsedSeconds(done, now)).toBe(30);
  });
  it("formats m:ss and h:mm:ss", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(65.9)).toBe("1:05");
    expect(formatElapsed(3725)).toBe("1:02:05");
    expect(formatElapsed(null)).toBe("–:––");
  });
});

describe("sectionsSummary", () => {
  it("collapses consecutive repeats into a count", () => {
    const names = ["intro", "verse", "chorus", "chorus", "bridge"] as const;
    expect(sectionsSummary(names.map((name) => ({ name })))).toBe(
      "INTRO · ESTROFA · CORO ×2 · PUENTE",
    );
  });
  it("does not collapse separated repeats", () => {
    const names = ["verse", "chorus", "verse", "chorus"] as const;
    expect(sectionsSummary(names.map((name) => ({ name })))).toBe(
      "ESTROFA · CORO · ESTROFA · CORO",
    );
  });
  it("prefers a custom label and handles empty input", () => {
    expect(sectionsSummary([{ name: "verse", label: " Estribillo " }])).toBe("ESTRIBILLO");
    expect(sectionsSummary([])).toBe("");
  });
});

describe("job tracking", () => {
  it("prefers the URL over stored ids", () => {
    const stored = { analyze: "sa", separate: "ss" };
    expect(resolveTracked({ a: "qa" }, stored)).toEqual({ analyze: "qa", separate: "ss" });
    expect(resolveTracked({ a: ["x", "y"], s: "" }, null)).toEqual({ analyze: "x", separate: null });
  });
  it("lets an artifact stand in for a missing job", () => {
    expect(rowView("analyze", null, true, 0).status).toBe("finished");
    expect(rowView("separate", null, false, 0).status).toBe("untracked");
    expect(rowView("separate", null, false, 0, true).status).toBe("checking");
    expect(rowView("separate", null, true, 0, true).status).toBe("finished");
    expect(rowView("analyze", job(), true, Date.parse("2026-10-26T10:00:10Z")).status).toBe("running");
  });
  it("leaves checking as soon as a job answers, an artifact exists or the job is lost", () => {
    expect(rowView("analyze", job({ status: "queued" }), false, 0, true).status).toBe("queued");
    expect(rowView("analyze", job({ status: "failed" }), false, 0, true).status).toBe("failed");
    expect(rowView("separate", null, true, 0, true).status).toBe("finished");
    // A lost job (404) is reported as "not awaiting" by the caller: nothing left to follow.
    expect(rowView("separate", null, false, 0, false).status).toBe("untracked");
  });
});
