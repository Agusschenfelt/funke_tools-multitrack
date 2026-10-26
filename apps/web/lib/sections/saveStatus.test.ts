import { describe, expect, it } from "vitest";
import { statusAfterEdit, type SaveStatus } from "./saveStatus";

describe("statusAfterEdit", () => {
  it("clears a stale saved or error status", () => {
    expect(statusAfterEdit({ phase: "saved" })).toEqual({ phase: "idle" });
    expect(statusAfterEdit({ phase: "error", message: "x" })).toEqual({ phase: "idle" });
  });
  it("keeps a save in flight", () => {
    const saving: SaveStatus = { phase: "saving" };
    expect(statusAfterEdit(saving)).toBe(saving);
  });
});
