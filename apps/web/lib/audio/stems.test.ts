import { describe, expect, it } from "vitest";
import { orderStems, stemNameOf } from "./stems";

const link = (name: string) => ({ name, url: `/files/${name}`, token_expires_at: "" });

describe("stems", () => {
  it("orders known stems for the lanes and makes URLs absolute", () => {
    const stems = orderStems([link("vocals.wav"), link("bass.wav"), link("drums.wav"), link("x.txt")]);
    expect(stems.map((s) => s.name)).toEqual(["drums", "bass", "vocals"]);
    expect(stems[0].url).toMatch(/^https?:\/\/.+\/files\/drums\.wav$/);
  });
  it("recognises stem file names only", () => {
    expect(stemNameOf("Guitar.WAV")).toBe("guitar");
    expect(stemNameOf("click.wav")).toBeNull();
  });
});
