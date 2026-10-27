import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StudioEngine } from "./engine";
import type { StemSource } from "./stems";

class FakeSource {
  started = false;
  stopped = false;
  disconnected = false;
  buffer: unknown = null;
  loop = false;
  loopStart = 0;
  loopEnd = 0;
  startedAt: number | null = null;
  offset: number | null = null;
  onended: (() => void) | null = null;
  connect() {}
  disconnect() {
    this.disconnected = true;
  }
  start(when?: number, offset?: number) {
    this.started = true;
    this.startedAt = when ?? null;
    this.offset = offset ?? null;
  }
  stop() {
    this.stopped = true;
  }
}

class FakeGain {
  disconnected = false;
  gain = {
    value: 1,
    setTargetAtTime() {},
    setValueAtTime() {},
    linearRampToValueAtTime() {},
  };
  connect() {}
  disconnect() {
    this.disconnected = true;
  }
}

const created = { sources: [] as FakeSource[], gains: [] as FakeGain[], contexts: [] as FakeContext[] };
let decodeFails: Set<number> = new Set();
let decodeCalls = 0;
let failConstruct = false;
let decodedFrames: number | null = null;
let createdBuffers: { length: number; copied: Float32Array[] }[] = [];

const pans: { pan: { value: number; targets: number[] }; disconnected: boolean }[] = [];

class FakeContext {
  currentTime = 0;
  state = "running";
  sampleRate = 44100;
  destination = {};
  closed = false;
  constructor() {
    if (failConstruct) throw new Error("AudioContext unsupported");
    created.contexts.push(this);
  }
  createGain() {
    const gain = new FakeGain();
    created.gains.push(gain);
    return gain;
  }
  createStereoPanner() {
    const panner = {
      disconnected: false,
      pan: {
        value: 0,
        targets: [] as number[],
        setTargetAtTime(value: number) {
          panner.pan.targets.push(value);
        },
      },
      connect() {},
      disconnect() {
        panner.disconnected = true;
      },
    };
    pans.push(panner);
    return panner;
  }
  createBufferSource() {
    const source = new FakeSource();
    created.sources.push(source);
    return source;
  }
  createBuffer(_channels: number, length: number, rate: number) {
    const buffer = {
      length,
      duration: length / rate,
      copied: [] as Float32Array[],
      copyToChannel(data: Float32Array) {
        buffer.copied.push(data);
      },
    };
    createdBuffers.push(buffer);
    return buffer;
  }
  async resume() {}
  async close() {
    this.closed = true;
    this.state = "closed";
  }
  async decodeAudioData(data: ArrayBuffer) {
    const call = decodeCalls++;
    if (decodeFails.has(call) || data.byteLength === 0) throw new Error("bad audio");
    if (decodedFrames !== null) {
      const ramp = Float32Array.from({ length: decodedFrames }, (_, i) => i);
      return {
        length: decodedFrames,
        duration: decodedFrames / 44100,
        numberOfChannels: 1,
        sampleRate: 44100,
        getChannelData: () => ramp,
      };
    }
    return {
      duration: 10,
      numberOfChannels: 1,
      sampleRate: 44100,
      getChannelData: () => new Float32Array(441),
    };
  }
}

const sources: StemSource[] = [
  { name: "drums", url: "http://x/drums" },
  { name: "bass", url: "http://x/bass" },
  { name: "vocals", url: "http://x/vocals" },
];

function stubFetch(statusByName: Record<string, number | "reject"> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const outcome = statusByName[url.split("/").pop() as string] ?? 200;
      if (outcome === "reject") throw new TypeError("offline");
      return new Response(outcome === 200 ? new Uint8Array([1, 2, 3, 4]) : "", { status: outcome });
    }),
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  created.sources = [];
  created.gains = [];
  created.contexts = [];
  decodeFails = new Set();
  decodeCalls = 0;
  failConstruct = false;
  decodedFrames = null;
  createdBuffers = [];
  pans.length = 0;
  vi.stubGlobal("AudioContext", FakeContext);
  stubFetch();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const ready = async (engine: StudioEngine, signal = new AbortController().signal) => {
  await engine.load(sources, signal);
  expect(engine.getSnapshot().status).toBe("ready");
};

describe("StudioEngine.load failure paths", () => {
  it("reports an HTTP error on its own stem and lets the others finish", async () => {
    stubFetch({ bass: 403 });
    const engine = new StudioEngine();
    await engine.load(sources, new AbortController().signal);
    const state = engine.getSnapshot();
    expect(state.stems.bass).toMatchObject({ phase: "error", failure: "expired" });
    expect(state.stems.drums.phase).toBe("ready");
    expect(state.stems.vocals.phase).toBe("ready");
    expect(state).toMatchObject({ status: "error", failure: "expired" });
    engine.dispose();
  });

  it("reports a network error per stem", async () => {
    stubFetch({ vocals: "reject" });
    const engine = new StudioEngine();
    await engine.load(sources, new AbortController().signal);
    const state = engine.getSnapshot();
    expect(state.stems.vocals).toMatchObject({ phase: "error", failure: "network" });
    expect(state.stems.drums.phase).toBe("ready");
    expect(state.failure).toBe("network");
    engine.dispose();
  });

  it("reports a decode error per stem", async () => {
    decodeFails = new Set([1]);
    const engine = new StudioEngine();
    await engine.load(sources, new AbortController().signal);
    const state = engine.getSnapshot();
    const failed = sources.filter((s) => state.stems[s.name].phase === "error");
    expect(failed).toHaveLength(1);
    expect(state.stems[failed[0].name].failure).toBe("decode");
    expect(state).toMatchObject({ status: "error", failure: "decode" });
    expect(sources.filter((s) => state.stems[s.name].phase === "ready")).toHaveLength(2);
    engine.dispose();
  });

  it("stays quiet when the load is aborted", async () => {
    const abort = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: { signal: AbortSignal }) => {
        abort.abort();
        init.signal.throwIfAborted();
        return new Response("");
      }),
    );
    const engine = new StudioEngine();
    await engine.load(sources, abort.signal);
    const state = engine.getSnapshot();
    expect(state.status).toBe("loading");
    expect(state.failure).toBeNull();
    engine.dispose();
  });

  it("ends in error instead of rejecting when no AudioContext can be built", async () => {
    failConstruct = true;
    const engine = new StudioEngine();
    await expect(engine.load(sources, new AbortController().signal)).resolves.toBeUndefined();
    expect(engine.getSnapshot()).toMatchObject({ status: "error", failure: "unsupported" });
    engine.dispose();
  });
});

describe("StudioEngine.load with compressed previews", () => {
  const alignment = { samples: 5000, primingSamples: 1024, sampleRate: 44100 };
  const preview: StemSource[] = [{ name: "drums", url: "http://x/drums", alignment }];

  it("cuts the encoder delay when the decoder returned it", async () => {
    decodedFrames = 5000 + 1024 + 300;
    const engine = new StudioEngine();
    await engine.load(preview, new AbortController().signal);
    expect(engine.getSnapshot().status).toBe("ready");
    const aligned = createdBuffers.find((b) => b.length === 5000);
    expect(aligned).toBeDefined();
    expect(aligned?.copied[0][0]).toBe(1024);
  });

  it("leaves the buffer alone when the decoder already hid the delay", async () => {
    decodedFrames = 5000 + 200;
    const engine = new StudioEngine();
    await engine.load(preview, new AbortController().signal);
    expect(engine.getSnapshot().status).toBe("ready");
    expect(createdBuffers.filter((b) => b.length === 5000)).toHaveLength(0);
  });
});

describe("StudioEngine.load while playing", () => {
  it("stops playback and leaves no sound source from the old song", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    await engine.play();
    expect(engine.getSnapshot().playing).toBe(true);
    const playing = [...created.sources];
    expect(playing.length).toBe(3);
    const oldGains = [...created.gains];

    await ready(engine);
    expect(engine.getSnapshot().playing).toBe(false);
    expect(playing.every((s) => s.stopped && s.disconnected)).toBe(true);
    expect(oldGains.filter((g) => g.disconnected).length).toBeGreaterThanOrEqual(3);
    expect(engine.getPosition()).toBe(0);
    // Nothing keeps ticking after the reload.
    expect(vi.getTimerCount()).toBe(0);
    engine.dispose();
  });

  it("a play that was still resuming does not start sources after a reload", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    const pending = engine.play();
    await engine.load(sources, new AbortController().signal);
    await pending;
    expect(engine.getSnapshot().playing).toBe(false);
    engine.dispose();
  });
});

describe("StudioEngine.dispose", () => {
  it("makes every later call a no-op", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.dispose();
    const contexts = created.contexts.length;

    await expect(engine.load(sources, new AbortController().signal)).resolves.toBeUndefined();
    await engine.play();
    engine.seek(3);
    engine.setClick(true);
    engine.setCues(true);
    engine.toggleMute("drums");
    expect(created.contexts.length).toBe(contexts);
    expect(engine.getSnapshot()).toMatchObject({ status: "idle", playing: false, clickOn: false });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("drops results of a load that finishes after dispose", async () => {
    const engine = new StudioEngine();
    const loading = engine.load(sources, new AbortController().signal);
    engine.dispose();
    await loading;
    expect(engine.getSnapshot().status).toBe("idle");
  });

  it("closes the audio context", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.dispose();
    expect(created.contexts[0].closed).toBe(true);
  });
});

describe("StudioEngine pan and presets", () => {
  it("builds one panner per stem and moves it with setPan", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    expect(pans).toHaveLength(3);
    engine.setPan("bass", -0.5);
    expect(engine.getSnapshot().mix.bass.pan).toBe(-0.5);
    expect(pans.filter((p) => p.pan.targets.includes(-0.5))).toHaveLength(1);
    engine.setPan("bass", 9);
    expect(engine.getSnapshot().mix.bass.pan).toBe(1);
    engine.dispose();
  });

  it("restores saved pans, ignoring unknown values", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.restorePans({ drums: 0.4, vocals: -2 });
    const { mix } = engine.getSnapshot();
    expect(mix.drums.pan).toBe(0.4);
    expect(mix.vocals.pan).toBe(-1);
    expect(mix.bass.pan).toBe(0);
    engine.dispose();
  });

  it("plays centred when the browser has no StereoPannerNode", async () => {
    const proto = FakeContext.prototype as unknown as { createStereoPanner?: unknown };
    const original = proto.createStereoPanner;
    proto.createStereoPanner = undefined;
    const engine = new StudioEngine();
    await ready(engine);
    expect(pans).toHaveLength(0);
    engine.setPan("drums", 0.5);
    engine.dispose();
    proto.createStereoPanner = original;
  });

  it("applies a preset to the lanes it has", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.toggleSolo("bass");
    engine.applyPreset("karaoke");
    const { mix } = engine.getSnapshot();
    expect(mix.vocals.muted).toBe(true);
    expect(mix.drums.muted).toBe(false);
    expect(mix.bass.solo).toBe(false);
    engine.dispose();
  });
});

describe("StudioEngine loop A-B", () => {
  const loop = { start: 10, end: 12 };

  beforeEach(() => {
    // A 20 s song, so the loop fits inside it.
    decodedFrames = 44100 * 20;
  });

  it("starts the stems looping inside the range", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.setLoop(loop);
    expect(engine.getSnapshot().loop).toEqual(loop);
    await engine.play();
    expect(created.sources).toHaveLength(3);
    for (const source of created.sources) {
      expect(source).toMatchObject({ loop: true, loopStart: 10, loopEnd: 12, offset: 10 });
    }
    engine.dispose();
  });

  it("wraps the reported position at the loop end", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.seek(11);
    engine.setLoop(loop);
    await engine.play();
    created.contexts[0].currentTime = 0.06 + 0.5;
    expect(engine.getPosition()).toBeCloseTo(11.5, 6);
    created.contexts[0].currentTime = 0.06 + 1.5;
    expect(engine.getPosition()).toBeCloseTo(10.5, 6);
    engine.dispose();
  });

  it("clears a range that is too short to be a loop", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.setLoop({ start: 5, end: 5.1 });
    expect(engine.getSnapshot().loop).toBeNull();
    engine.dispose();
  });

  it("paused: moves the playhead to the loop start when it is outside", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.seek(3);
    engine.setLoop(loop);
    expect(engine.getPosition()).toBe(10);
    engine.dispose();
  });

  it("playing: a range that holds the playhead applies without restarting", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.seek(11);
    await engine.play();
    const sources = [...created.sources];
    created.contexts[0].currentTime = 0.06 + 0.25;
    engine.setLoop(loop);
    expect(created.sources).toHaveLength(sources.length);
    expect(sources.every((s) => s.loop && s.loopStart === 10 && s.loopEnd === 12 && !s.stopped)).toBe(true);
    expect(engine.getPosition()).toBeCloseTo(11.25, 6);
    created.contexts[0].currentTime = 0.06 + 1.25;
    expect(engine.getPosition()).toBeCloseTo(10.25, 6);
    engine.dispose();
  });

  it("playing: a range away from the playhead restarts inside it", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    await engine.play();
    const first = [...created.sources];
    engine.setLoop(loop);
    expect(first.every((s) => s.stopped)).toBe(true);
    expect(created.sources.slice(first.length).map((s) => s.offset)).toEqual([10, 10, 10]);
    expect(engine.getPosition()).toBe(10);
    engine.dispose();
  });

  it("clearing it while playing lets the stems run on without a gap", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.seek(11);
    engine.setLoop(loop);
    await engine.play();
    const sources = [...created.sources];
    created.contexts[0].currentTime = 0.06 + 1.5;
    engine.clearLoop();
    expect(engine.getSnapshot().loop).toBeNull();
    expect(sources.every((s) => !s.loop && !s.stopped)).toBe(true);
    expect(engine.getPosition()).toBeCloseTo(10.5, 6);
    created.contexts[0].currentTime += 1;
    expect(engine.getPosition()).toBeCloseTo(11.5, 6);
    engine.dispose();
  });

  it("seeking outside the loop drops it; inside keeps it", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.setLoop(loop);
    engine.seek(11.5);
    expect(engine.getSnapshot().loop).toEqual(loop);
    engine.seek(20);
    expect(engine.getSnapshot().loop).toBeNull();
    engine.dispose();
  });

  it("schedules clicks on both sides of the wrap", async () => {
    const engine = new StudioEngine();
    await ready(engine);
    engine.setTimeline({
      beats: [],
      clicks: [
        { time: 10.1, accent: false },
        { time: 10.6, accent: false },
        { time: 11.8, accent: true },
      ],
      cues: [],
    });
    engine.seek(11.5);
    engine.setLoop(loop);
    await engine.play();
    const ctx = created.contexts[0];
    for (let step = 0; step < 26; step += 1) {
      ctx.currentTime += 0.1;
      vi.advanceTimersByTime(25);
    }
    const clicks = created.sources.slice(3).map((s) => s.startedAt as number);
    // 11.8 is 0.3 s after the start; the wrap at 12.0 comes 0.5 s in, so 10.1 and 10.6 follow at
    // 0.6 s and 1.1 s; the next lap (2 s long) brings 11.8 again 2.3 s in.
    const base = 0.06;
    const expected = [0.3, 0.6, 1.1, 2.3].map((t) => base + t);
    expect(clicks.slice(0, 4).map((t) => Math.round(t * 1000) / 1000)).toEqual(
      expected.map((t) => Math.round(t * 1000) / 1000),
    );
    engine.dispose();
  });
});
