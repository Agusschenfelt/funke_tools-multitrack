import { describe, expect, it, vi } from "vitest";
import { DEFAULT_MIX, type StemMix } from "./mix";
import {
  encodeWav,
  guardDb,
  levelGuard,
  mixdownStems,
  mixFilename,
  peakOf,
  renderMixdown,
  wavSize,
} from "./mixdown";
import type { StemName } from "./stems";

const mix = (over: Partial<Record<StemName, Partial<StemMix>>> = {}) => {
  const names: StemName[] = ["drums", "bass", "vocals"];
  return Object.fromEntries(names.map((n) => [n, { ...DEFAULT_MIX, ...over[n] }])) as Record<
    StemName,
    StemMix
  >;
};

const buffers = new Map<StemName, { length: number }>([
  ["drums", { length: 100 }],
  ["bass", { length: 120 }],
  ["vocals", { length: 90 }],
]);
const order: StemName[] = ["drums", "bass", "vocals"];

describe("mixdownStems", () => {
  it("keeps every stem at its volume and pan by default", () => {
    const stems = mixdownStems(order, mix({ bass: { volume: 0.5, pan: -0.25 } }), buffers);
    expect(stems.map((s) => [s.name, s.gain, s.pan])).toEqual([
      ["drums", 1, 0],
      ["bass", 0.5, -0.25],
      ["vocals", 1, 0],
    ]);
  });

  it("leaves out muted stems", () => {
    expect(mixdownStems(order, mix({ drums: { muted: true } }), buffers).map((s) => s.name)).toEqual([
      "bass",
      "vocals",
    ]);
  });

  it("with a solo only the soloed stem remains, even if it was muted", () => {
    const stems = mixdownStems(order, mix({ vocals: { solo: true, muted: true } }), buffers);
    expect(stems.map((s) => s.name)).toEqual(["vocals"]);
  });

  it("skips stems that failed to load and clamps pan", () => {
    const partial = new Map(buffers);
    partial.delete("bass");
    const stems = mixdownStems(order, mix({ drums: { pan: 7 } }), partial);
    expect(stems.map((s) => s.name)).toEqual(["drums", "vocals"]);
    expect(stems[0].pan).toBe(1);
  });

  it("returns nothing for an all-muted mix", () => {
    const silent = mix({ drums: { muted: true }, bass: { muted: true }, vocals: { muted: true } });
    expect(mixdownStems(order, silent, buffers)).toEqual([]);
  });
});

describe("level guard", () => {
  it("does nothing while the mix fits", () => {
    expect(peakOf([Float32Array.of(0.2, -0.9), Float32Array.of(0.5)])).toBeCloseTo(0.9);
    expect(levelGuard(0.9)).toBe(1);
    expect(guardDb(1)).toBe(0);
  });

  it("brings an over-full mix back to full scale", () => {
    expect(levelGuard(2)).toBe(0.5);
    expect(guardDb(0.5)).toBeCloseTo(6.02, 2);
  });
});

describe("encodeWav", () => {
  const read = (buffer: ArrayBuffer) => new DataView(buffer);
  const tag = (view: DataView, at: number) =>
    String.fromCharCode(...[0, 1, 2, 3].map((i) => view.getUint8(at + i)));

  it("writes a 16-bit stereo header and samples", () => {
    const left = Float32Array.of(0, 0.5, -0.5, 1);
    const right = Float32Array.of(0, -1, 0.25, -0.25);
    const buffer = encodeWav([left, right], 44100, 16);
    const view = read(buffer);
    expect(buffer.byteLength).toBe(wavSize(4, 16));
    expect([tag(view, 0), tag(view, 8), tag(view, 12), tag(view, 36)]).toEqual(["RIFF", "WAVE", "fmt ", "data"]);
    expect(view.getUint32(4, true)).toBe(buffer.byteLength - 8);
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(2);
    expect(view.getUint32(24, true)).toBe(44100);
    expect(view.getUint32(28, true)).toBe(44100 * 4);
    expect(view.getUint16(32, true)).toBe(4);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(16);
    // Interleaved L R L R ...; full scale positive clips to 32767.
    expect(view.getInt16(44 + 4, true)).toBe(16384);
    expect(view.getInt16(44 + 6, true)).toBe(-32768);
    expect(view.getInt16(44 + 12, true)).toBe(32767);
  });

  it("writes 24-bit little-endian samples", () => {
    const buffer = encodeWav([Float32Array.of(0.5, -0.5), Float32Array.of(0, 1)], 48000, 24);
    const view = read(buffer);
    expect(buffer.byteLength).toBe(wavSize(2, 24));
    expect(view.getUint16(34, true)).toBe(24);
    expect(view.getUint16(32, true)).toBe(6);
    const int24 = (at: number) => {
      const value = view.getUint8(at) | (view.getUint8(at + 1) << 8) | (view.getUint8(at + 2) << 16);
      return value & 0x800000 ? value - 0x1000000 : value;
    };
    expect(int24(44)).toBe(4194304);
    expect(int24(44 + 3)).toBe(0);
    expect(int24(44 + 6)).toBe(-4194304);
    expect(int24(44 + 9)).toBe(8388607);
  });

  it("applies the level guard scale", () => {
    const buffer = encodeWav([Float32Array.of(1.5), Float32Array.of(-1.5)], 44100, 16, levelGuard(1.5));
    const view = read(buffer);
    expect(view.getInt16(44, true)).toBe(32767);
    expect(view.getInt16(46, true)).toBe(-32768);
  });

  it("clips whatever the scale left above full scale", () => {
    const view = read(encodeWav([Float32Array.of(3)], 44100, 16));
    expect(view.getInt16(44, true)).toBe(32767);
  });

  it("writes mono as one channel", () => {
    const view = read(encodeWav([Float32Array.of(0.25)], 44100, 16));
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint16(32, true)).toBe(2);
  });
});

describe("mixFilename", () => {
  it("names the mix after the song", () => {
    expect(mixFilename("Mi canción")).toBe("Mi canción - mezcla.wav");
  });

  it("drops characters file systems reject and falls back for empty titles", () => {
    expect(mixFilename('a/b:c*"d"?')).toBe("a b c d - mezcla.wav");
    expect(mixFilename("  ... ")).toBe("Mi tema - mezcla.wav");
  });
});

/* ------------------------------------------------------ fake offline */

class FakeNode {
  connections: unknown[] = [];
  gain = { value: 1, events: [] as string[], setValueAtTime() {}, linearRampToValueAtTime() {} };
  pan = { value: 0 };
  buffer: unknown = null;
  startedAt: number | null = null;
  offset: number | null = null;
  connect(to: unknown) {
    this.connections.push(to);
  }
  start(when: number, offset?: number) {
    this.startedAt = when;
    this.offset = offset ?? null;
  }
}

function fakeContext(length: number, rate: number) {
  const sources: FakeNode[] = [];
  const gains: FakeNode[] = [];
  const panners: FakeNode[] = [];
  const suspends: number[] = [];
  const destination = { name: "destination" };
  const pending: Promise<void>[] = [];
  const ctx = {
    destination,
    createBufferSource: () => {
      const n = new FakeNode();
      sources.push(n);
      return n;
    },
    createGain: () => {
      const n = new FakeNode();
      gains.push(n);
      return n;
    },
    createStereoPanner: () => {
      const n = new FakeNode();
      panners.push(n);
      return n;
    },
    suspend(time: number) {
      suspends.push(time);
      const p = Promise.resolve();
      pending.push(p);
      return p;
    },
    resume: vi.fn(async () => {}),
    async startRendering() {
      await Promise.all(pending);
      const channels = [new Float32Array(length), new Float32Array(length)];
      return { numberOfChannels: 2, sampleRate: rate, getChannelData: (i: number) => channels[i] };
    },
  };
  return { ctx: ctx as unknown as OfflineAudioContext, sources, gains, panners, suspends, destination };
}

describe("renderMixdown", () => {
  const stem = (name: StemName, gain: number, pan: number) => ({
    name,
    gain,
    pan,
    buffer: { id: name } as unknown as AudioBuffer,
  });

  it("wires each audible stem through its gain and pan to the output", async () => {
    const fake = fakeContext(1000, 44100);
    const result = await renderMixdown({
      stems: [stem("drums", 0.5, -1), stem("vocals", 1, 0.25)],
      length: 1000,
      sampleRate: 44100,
      createContext: () => fake.ctx,
    });
    expect(fake.sources.map((s) => s.startedAt)).toEqual([0, 0]);
    expect(fake.gains.map((g) => g.gain.value)).toEqual([0.5, 1]);
    expect(fake.panners.map((p) => p.pan.value)).toEqual([-1, 0.25]);
    expect(fake.panners[0].connections).toEqual([fake.destination]);
    expect(result.channels).toHaveLength(2);
    expect(result.sampleRate).toBe(44100);
  });

  it("schedules click and cues at their song time, skipping the cue's leading silence", async () => {
    const fake = fakeContext(1000, 44100);
    const click = { id: "click" } as unknown as AudioBuffer;
    const cue = { id: "cue" } as unknown as AudioBuffer;
    await renderMixdown({
      stems: [],
      length: 1000,
      sampleRate: 44100,
      click: {
        buffers: { accent: click, normal: click },
        events: [
          { time: 0.5, accent: true },
          { time: 1, accent: false },
        ],
      },
      cues: {
        library: new Map([["chorus", { buffer: cue, onset: 0.1 }]]),
        placements: [{ time: 2, name: "chorus" }],
      },
      createContext: () => fake.ctx,
    });
    expect(fake.sources.map((s) => [s.startedAt, s.offset])).toEqual([
      [0.5, null],
      [1, null],
      [2, 0.1],
    ]);
  });

  it("reports progress through suspend points on render-block edges and ends at 1", async () => {
    const rate = 44100;
    const length = rate * 10;
    const fake = fakeContext(length, rate);
    const seen: number[] = [];
    await renderMixdown({
      stems: [],
      length,
      sampleRate: rate,
      onProgress: (f) => seen.push(f),
      createContext: () => fake.ctx,
    });
    expect(fake.suspends.length).toBe(2);
    expect(fake.suspends.every((t) => Math.round(t * rate) % 128 === 0)).toBe(true);
    expect(seen.at(-1)).toBe(1);
    expect(seen.slice(0, -1).every((f, i, a) => f > 0 && f < 1 && (i === 0 || f > a[i - 1]))).toBe(true);
    expect(fake.ctx.resume).toHaveBeenCalled();
  });

  it("rejects when cancelled", async () => {
    const abort = new AbortController();
    abort.abort();
    await expect(
      renderMixdown({
        stems: [],
        length: 10,
        sampleRate: 44100,
        signal: abort.signal,
        createContext: () => fakeContext(10, 44100).ctx,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});
