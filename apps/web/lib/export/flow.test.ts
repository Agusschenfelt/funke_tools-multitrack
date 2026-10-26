import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { exportBlockedBy, packFailureMessage, startProblem } from "./flow";

describe("startProblem", () => {
  it("treats 409 as missing artifacts and everything else as other", () => {
    expect(startProblem(new ApiError("http", 409))).toBe("missing");
    expect(startProblem(new ApiError("http", 503))).toBe("other");
    expect(startProblem(new ApiError("network", null))).toBe("other");
    expect(startProblem(new Error("x"))).toBe("other");
  });
});

describe("packFailureMessage", () => {
  it("never shows raw server text", () => {
    expect(packFailureMessage("Traceback: KeyError 'x'")).toBe("No se pudo armar el pack. Probá de nuevo.");
    expect(packFailureMessage(null)).toBe("No se pudo armar el pack. Probá de nuevo.");
  });

  it("explains the recognisable causes", () => {
    expect(packFailureMessage("job timed out")).toMatch(/tardó demasiado/);
    expect(packFailureMessage("analysis has no usable beat grid")).toMatch(/grilla/);
  });
});

describe("exportBlockedBy", () => {
  it("blocks while there are unsaved or saving edits", () => {
    expect(exportBlockedBy({ dirty: false, saving: false })).toBeNull();
    expect(exportBlockedBy({ dirty: true, saving: false })).toBe("dirty");
    expect(exportBlockedBy({ dirty: false, saving: true })).toBe("saving");
    expect(exportBlockedBy({ dirty: true, saving: true })).toBe("saving");
  });
});
