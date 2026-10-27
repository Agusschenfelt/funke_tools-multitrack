import { describe, expect, it, vi } from "vitest";
import {
  StemLoadError,
  decodeStemBytes,
  exactBuffer,
  fetchStemBytes,
  loadStems,
  previewWindow,
  readBytes,
} from "./stemLoad";
import type { StemSource } from "./stems";

const noop = () => {};

function streamed(chunks: Uint8Array[], contentLength?: number): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
  const headers: Record<string, string> =
    contentLength === undefined ? {} : { "content-length": String(contentLength) };
  return new Response(stream, { headers });
}

describe("exactBuffer", () => {
  it("copies only the bytes of a subarray, not the whole backing buffer", () => {
    const backing = new Uint8Array([9, 9, 1, 2, 3, 9, 9]);
    const view = backing.subarray(2, 5);
    expect(view.buffer.byteLength).toBe(7);
    const exact = exactBuffer(view);
    expect(Array.from(new Uint8Array(exact))).toEqual([1, 2, 3]);
  });

  it("returns the same buffer when the view covers it entirely", () => {
    const bytes = new Uint8Array([1, 2, 3]);
    expect(exactBuffer(bytes)).toBe(bytes.buffer);
  });
});

describe("readBytes", () => {
  it("joins chunks without a known length", async () => {
    const bytes = await readBytes(streamed([new Uint8Array([1, 2]), new Uint8Array([3])]), noop);
    expect(Array.from(bytes)).toEqual([1, 2, 3]);
    expect(bytes.buffer.byteLength).toBe(3);
  });

  it("fills a preallocated buffer when content-length is right", async () => {
    const progress: number[] = [];
    const bytes = await readBytes(
      streamed([new Uint8Array([1, 2]), new Uint8Array([3, 4])], 4),
      (n) => progress.push(n),
    );
    expect(Array.from(bytes)).toEqual([1, 2, 3, 4]);
    expect(progress).toEqual([2, 4]);
  });

  it("does not hand over the unused tail when the body is shorter than announced", async () => {
    const bytes = await readBytes(streamed([new Uint8Array([1, 2, 3])], 10), noop);
    expect(Array.from(bytes)).toEqual([1, 2, 3]);
    expect(bytes.buffer.byteLength).toBe(3);
  });

  it("handles a body longer than announced", async () => {
    const bytes = await readBytes(streamed([new Uint8Array([1, 2]), new Uint8Array([3, 4])], 3), noop);
    expect(Array.from(bytes)).toEqual([1, 2, 3, 4]);
    expect(bytes.buffer.byteLength).toBe(4);
  });
});

describe("fetchStemBytes", () => {
  const signal = new AbortController().signal;
  const bodyOf = (n: number[]) => new Response(new Uint8Array(n));

  it("returns the bytes", async () => {
    const bytes = await fetchStemBytes("u", signal, noop, async () => bodyOf([1, 2]));
    expect(Array.from(bytes)).toEqual([1, 2]);
  });

  it("maps a 4xx to expired and a 5xx to network", async () => {
    await expect(
      fetchStemBytes("u", signal, noop, async () => new Response("", { status: 403 })),
    ).rejects.toMatchObject({ failure: "expired" });
    await expect(
      fetchStemBytes("u", signal, noop, async () => new Response("", { status: 502 })),
    ).rejects.toMatchObject({ failure: "network" });
  });

  it("maps a rejected fetch and an abort to network errors", async () => {
    await expect(
      fetchStemBytes("u", signal, noop, async () => Promise.reject(new TypeError("offline"))),
    ).rejects.toMatchObject({ failure: "network" });
    await expect(
      fetchStemBytes("u", signal, noop, async () =>
        Promise.reject(new DOMException("aborted", "AbortError")),
      ),
    ).rejects.toBeInstanceOf(StemLoadError);
  });
});

describe("decodeStemBytes", () => {
  it("decodes exactly the used bytes of a subarray", async () => {
    const view = new Uint8Array([7, 7, 1, 2, 7]).subarray(2, 4);
    const seen: number[][] = [];
    await decodeStemBytes(async (data) => {
      seen.push(Array.from(new Uint8Array(data)));
      return "buffer";
    }, view);
    expect(seen).toEqual([[1, 2]]);
  });

  it("maps a decode error", async () => {
    await expect(
      decodeStemBytes(async () => Promise.reject(new Error("bad data")), new Uint8Array(1)),
    ).rejects.toMatchObject({ failure: "decode" });
  });
});

describe("loadStems", () => {
  const sources: StemSource[] = [
    { name: "drums", url: "d" },
    { name: "bass", url: "b" },
    { name: "vocals", url: "v" },
  ];

  it("records each failure under its stem and lets the others finish", async () => {
    const done: string[] = [];
    const reported: [string, string][] = [];
    const failures = await loadStems(
      sources,
      3,
      new AbortController().signal,
      async ({ name }) => {
        if (name === "bass") throw new StemLoadError("expired");
        if (name === "vocals") throw new StemLoadError("decode");
        done.push(name);
      },
      (name, failure) => reported.push([name, failure]),
    );
    expect(done).toEqual(["drums"]);
    expect(failures).toEqual({ bass: "expired", vocals: "decode" });
    expect(reported).toEqual([
      ["bass", "expired"],
      ["vocals", "decode"],
    ]);
  });

  it("treats an unknown error as a network failure", async () => {
    const failures = await loadStems(
      [sources[0]],
      1,
      new AbortController().signal,
      async () => Promise.reject(new Error("???")),
      noop,
    );
    expect(failures).toEqual({ drums: "network" });
  });

  it("ignores failures after an abort and skips pending stems", async () => {
    const abort = new AbortController();
    const onFailure = vi.fn();
    const load = vi.fn(async () => {
      abort.abort();
      throw new StemLoadError("network");
    });
    const failures = await loadStems(sources, 1, abort.signal, load, onFailure);
    expect(load).toHaveBeenCalledOnce();
    expect(onFailure).not.toHaveBeenCalled();
    expect(failures).toEqual({});
  });

  it("never runs more than `size` at once", async () => {
    let active = 0;
    let peak = 0;
    await loadStems(
      sources,
      2,
      new AbortController().signal,
      async () => {
        active += 1;
        peak = Math.max(peak, active);
        await Promise.resolve();
        await Promise.resolve();
        active -= 1;
      },
      noop,
    );
    expect(peak).toBe(2);
  });
});

describe("previewWindow", () => {
  const alignment = { samples: 10_000, primingSamples: 1024 };

  it("keeps a preview whose decoder already hid the encoder delay", () => {
    expect(previewWindow(10_000, alignment)).toEqual({ start: 0, length: 10_000 });
    expect(previewWindow(10_000 + 1023, alignment)).toEqual({ start: 0, length: 11_023 });
  });

  it("cuts the encoder delay and the padding when the decoder kept them", () => {
    expect(previewWindow(10_000 + 1024, alignment)).toEqual({ start: 1024, length: 10_000 });
    expect(previewWindow(10_000 + 1024 + 700, alignment)).toEqual({ start: 1024, length: 10_000 });
  });
});
