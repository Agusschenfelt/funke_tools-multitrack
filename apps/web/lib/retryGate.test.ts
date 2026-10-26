import { describe, expect, it } from "vitest";
import { createRetryGate, withJob } from "./retryGate";

describe("createRetryGate", () => {
  it("only the newest ticket per row is current", () => {
    const gate = createRetryGate();
    const first = gate.begin("analyze");
    const second = gate.begin("analyze");
    expect(gate.isCurrent("analyze", first)).toBe(false);
    expect(gate.isCurrent("analyze", second)).toBe(true);
  });

  it("rows do not invalidate each other", () => {
    const gate = createRetryGate();
    const a = gate.begin("analyze");
    const s = gate.begin("separate");
    expect(gate.isCurrent("analyze", a)).toBe(true);
    expect(gate.isCurrent("separate", s)).toBe(true);
  });
});

describe("withJob", () => {
  it("replaces one id and keeps the other", () => {
    const next = withJob({ analyze: "a1", separate: "s1" }, "separate", "s2");
    expect(next).toEqual({ analyze: "a1", separate: "s2" });
  });
});
