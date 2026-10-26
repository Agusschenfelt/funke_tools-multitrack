/**
 * Web Audio studio engine.
 *
 * Playback: one AudioContext; every stem is an AudioBufferSourceNode started with the same `when`
 * and offset, so they run sample-synchronously from a single context time. Seek and resume build
 * new sources (a node plays once). Position is derived from the context clock, never from timers.
 *
 * Click and cues are scheduled with a lookahead scheduler: a 25 ms timer schedules every event
 * that falls in the next 300 ms against context time. Both go through their own bus gain, so the
 * toggles are instant and sample-accurate scheduling keeps running underneath.
 *
 * Memory: each stem is decoded once and kept as the AudioBuffer (float32, stereo). The encoded
 * bytes are dropped after decoding, peaks are a small fixed-size array, and downloads run three at
 * a time so the transient encoded copies stay bounded. Six stereo stems of four minutes are about
 * 500 MB of decoded audio; that is the floor of this design.
 */
import type { SectionName } from "@/lib/api";
import { clickWave } from "./click";
import { DEFAULT_MIX, stemGains, type StemMix } from "./mix";
import { bucketCount, computePeaks, type Peaks } from "./peaks";
import {
  eventsInWindow,
  leadingSilenceFrames,
  type ClickEvent,
  type CuePlacement,
} from "./schedule";
import { STEM_ORDER, type StemName, type StemSource } from "./stems";

const CONTEXT_RATE = 44100;
const LOOKAHEAD = 0.3;
const TICK_MS = 25;
const START_DELAY = 0.06;
const DOWNLOADS_AT_ONCE = 3;
const GAIN_SMOOTHING = 0.01;

export type StemPhase = "pending" | "downloading" | "decoding" | "ready";
export type LoadFailure = "expired" | "network" | "decode";
export type CueLanguage = "es" | "en";

export interface StemView {
  phase: StemPhase;
  /** Bytes received so far (the API does not expose Content-Length cross-origin). */
  loaded: number;
  peaks: Peaks | null;
}

export interface EngineState {
  status: "idle" | "loading" | "ready" | "error";
  failure: LoadFailure | null;
  /** Stems in lane order. */
  order: StemName[];
  stems: Record<StemName, StemView>;
  mix: Record<StemName, StemMix>;
  playing: boolean;
  duration: number;
  clickOn: boolean;
  cuesOn: boolean;
  cueLanguage: CueLanguage;
  cuesStatus: "idle" | "loading" | "ready" | "error";
}

export interface EngineTimeline {
  beats: readonly number[];
  clicks: readonly ClickEvent[];
  cues: readonly CuePlacement[];
}

interface CueSample {
  buffer: AudioBuffer;
  /** Seconds of leading silence to skip so the first sound is the speech onset. */
  onset: number;
}

interface Run {
  ctxStart: number;
  songStart: number;
  scheduledTo: number;
  sources: AudioBufferSourceNode[];
  oneShots: Set<AudioBufferSourceNode>;
  lastCue: GainNode | null;
}

class StemLoadError extends Error {
  readonly failure: LoadFailure;
  constructor(failure: LoadFailure) {
    super(failure);
    this.failure = failure;
  }
}

function emptyStems(): Record<StemName, StemView> {
  const out = {} as Record<StemName, StemView>;
  for (const name of STEM_ORDER) out[name] = { phase: "pending", loaded: 0, peaks: null };
  return out;
}

function defaultMix(): Record<StemName, StemMix> {
  const out = {} as Record<StemName, StemMix>;
  for (const name of STEM_ORDER) out[name] = { ...DEFAULT_MIX };
  return out;
}

function initialState(): EngineState {
  return {
    status: "idle",
    failure: null,
    order: [],
    stems: emptyStems(),
    mix: defaultMix(),
    playing: false,
    duration: 0,
    clickOn: false,
    cuesOn: false,
    cueLanguage: "es",
    cuesStatus: "idle",
  };
}

function stop(node: AudioBufferSourceNode) {
  try {
    node.stop();
  } catch {
    // Already stopped or never started.
  }
  node.disconnect();
}

async function readBytes(
  response: Response,
  onProgress: (loaded: number) => void,
): Promise<Uint8Array> {
  const total = Number(response.headers.get("content-length")) || 0;
  const reader = response.body?.getReader();
  if (!reader) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    onProgress(bytes.length);
    return bytes;
  }
  // With a known size, write chunks straight into one buffer; otherwise join them once at the end.
  let target = total > 0 ? new Uint8Array(total) : null;
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (target && received + value.length <= target.length) target.set(value, received);
    else {
      if (target) {
        chunks.push(target.subarray(0, received));
        target = null;
      }
      chunks.push(value);
    }
    received += value.length;
    onProgress(received);
  }
  if (target) return received === target.length ? target : target.subarray(0, received);
  const joined = new Uint8Array(received);
  let at = 0;
  for (const chunk of chunks) {
    joined.set(chunk, at);
    at += chunk.length;
  }
  return joined;
}

async function pool<T>(items: readonly T[], size: number, work: (item: T) => Promise<void>) {
  let next = 0;
  const lanes = Array.from({ length: Math.min(size, items.length) }, async () => {
    while (next < items.length) await work(items[next++]);
  });
  await Promise.all(lanes);
}

export class StudioEngine {
  private state: EngineState = initialState();
  private readonly serverState: EngineState = initialState();
  private readonly listeners = new Set<() => void>();

  private ctx: AudioContext | null = null;
  private clickBus: GainNode | null = null;
  private cueBus: GainNode | null = null;
  private clickBuffers: { accent: AudioBuffer; normal: AudioBuffer } | null = null;
  private readonly stemNodes = new Map<StemName, GainNode>();
  private readonly buffers = new Map<StemName, AudioBuffer>();
  private readonly cueLibrary = new Map<CueLanguage, Map<SectionName, CueSample>>();

  private timeline: EngineTimeline = { beats: [], clicks: [], cues: [] };
  private run: Run | null = null;
  private pausedAt = 0;
  private timer: ReturnType<typeof setInterval> | null = null;
  private loadAbort: AbortController | null = null;
  private playToken = 0;
  private cueToken = 0;

  /* ------------------------------------------------------------ store */

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  readonly getSnapshot = (): EngineState => this.state;
  readonly getServerSnapshot = (): EngineState => this.serverState;

  private set(patch: Partial<EngineState>) {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }

  private setStem(name: StemName, patch: Partial<StemView>) {
    this.set({ stems: { ...this.state.stems, [name]: { ...this.state.stems[name], ...patch } } });
  }

  /* ---------------------------------------------------------- context */

  private ensureContext(): AudioContext {
    if (this.ctx && this.ctx.state !== "closed") return this.ctx;
    const ctx = new AudioContext({ sampleRate: CONTEXT_RATE, latencyHint: "interactive" });
    this.ctx = ctx;
    this.clickBus = ctx.createGain();
    this.clickBus.gain.value = this.state.clickOn ? 1 : 0;
    this.clickBus.connect(ctx.destination);
    this.cueBus = ctx.createGain();
    this.cueBus.gain.value = this.state.cuesOn ? 1 : 0;
    this.cueBus.connect(ctx.destination);
    const make = (accent: boolean) => {
      const wave = clickWave(accent, ctx.sampleRate);
      const buffer = ctx.createBuffer(1, wave.length, ctx.sampleRate);
      buffer.copyToChannel(wave as Float32Array<ArrayBuffer>, 0);
      return buffer;
    };
    this.clickBuffers = { accent: make(true), normal: make(false) };
    this.stemNodes.clear();
    return ctx;
  }

  /* ---------------------------------------------------------- loading */

  setTimeline(timeline: EngineTimeline) {
    this.timeline = timeline;
  }

  async load(sources: readonly StemSource[], signal: AbortSignal): Promise<void> {
    this.loadAbort?.abort();
    const abort = new AbortController();
    this.loadAbort = abort;
    const onAbort = () => abort.abort();
    signal.addEventListener("abort", onAbort, { once: true });

    const ctx = this.ensureContext();
    this.buffers.clear();
    this.set({
      status: "loading",
      failure: null,
      order: sources.map((s) => s.name),
      stems: emptyStems(),
    });

    try {
      await pool(sources, DOWNLOADS_AT_ONCE, async (source) => {
        if (abort.signal.aborted) return;
        await this.loadStem(ctx, source, abort.signal);
      });
      if (abort.signal.aborted) return;
      let duration = 0;
      for (const buffer of this.buffers.values()) duration = Math.max(duration, buffer.duration);
      this.applyGains();
      this.set({ status: "ready", duration });
    } catch (error) {
      abort.abort();
      if (signal.aborted || this.loadAbort !== abort) return;
      this.set({
        status: "error",
        failure: error instanceof StemLoadError ? error.failure : "network",
      });
    } finally {
      signal.removeEventListener("abort", onAbort);
    }
  }

  private async loadStem(ctx: AudioContext, { name, url }: StemSource, signal: AbortSignal) {
    this.setStem(name, { phase: "downloading", loaded: 0 });
    let bytes: Uint8Array;
    try {
      const response = await fetch(url, { signal });
      if (!response.ok) {
        throw new StemLoadError(response.status >= 400 && response.status < 500 ? "expired" : "network");
      }
      bytes = await readBytes(response, (loaded) => this.setStem(name, { loaded }));
    } catch (error) {
      if (error instanceof StemLoadError) throw error;
      throw new StemLoadError("network");
    }
    if (signal.aborted) return;
    this.setStem(name, { phase: "decoding" });
    let buffer: AudioBuffer;
    try {
      buffer = await ctx.decodeAudioData(bytes.buffer as ArrayBuffer);
    } catch {
      throw new StemLoadError("decode");
    }
    if (signal.aborted) return;
    const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) =>
      buffer.getChannelData(i),
    );
    const peaks = computePeaks(channels, bucketCount(buffer.duration));
    const node = ctx.createGain();
    node.connect(ctx.destination);
    this.stemNodes.set(name, node);
    this.buffers.set(name, buffer);
    this.setStem(name, { phase: "ready", peaks });
  }

  /* --------------------------------------------------------- playback */

  getPosition(): number {
    const { run, ctx } = this;
    if (!run || !ctx) return this.pausedAt;
    const elapsed = Math.max(0, ctx.currentTime - run.ctxStart);
    return Math.min(this.state.duration, run.songStart + elapsed);
  }

  readonly toggle = () => {
    if (this.state.playing) this.pause();
    else void this.play();
  };

  async play(): Promise<void> {
    if (this.state.status !== "ready" || this.state.playing) return;
    const token = ++this.playToken;
    const ctx = this.ensureContext();
    try {
      await ctx.resume();
    } catch {
      return;
    }
    if (token !== this.playToken || this.state.playing) return;
    const from = this.pausedAt >= this.state.duration - 0.05 ? 0 : this.pausedAt;
    this.startRun(ctx, from);
    this.set({ playing: true });
  }

  pause() {
    this.playToken += 1;
    if (!this.run) return;
    this.pausedAt = this.getPosition();
    this.stopRun();
    this.set({ playing: false });
  }

  seek(seconds: number) {
    const target = Math.min(this.state.duration, Math.max(0, seconds));
    if (this.run && this.ctx) {
      this.stopRun();
      this.startRun(this.ctx, target);
    } else {
      this.pausedAt = target;
    }
  }

  private startRun(ctx: AudioContext, offset: number) {
    const ctxStart = ctx.currentTime + START_DELAY;
    const sources: AudioBufferSourceNode[] = [];
    for (const name of this.state.order) {
      const buffer = this.buffers.get(name);
      const node = this.stemNodes.get(name);
      if (!buffer || !node) continue;
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(node);
      source.start(ctxStart, offset);
      sources.push(source);
    }
    this.run = {
      ctxStart,
      songStart: offset,
      scheduledTo: offset,
      sources,
      oneShots: new Set(),
      lastCue: null,
    };
    this.timer = setInterval(this.tick, TICK_MS);
    this.tick();
  }

  private stopRun() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    const run = this.run;
    this.run = null;
    if (!run) return;
    for (const source of run.sources) stop(source);
    for (const source of run.oneShots) stop(source);
  }

  private readonly tick = () => {
    const { run, ctx } = this;
    if (!run || !ctx) return;
    if (this.getPosition() >= this.state.duration) {
      this.pausedAt = this.state.duration;
      this.stopRun();
      this.set({ playing: false });
      return;
    }
    const now = ctx.currentTime;
    const horizon = run.songStart + (now + LOOKAHEAD - run.ctxStart);
    const from = Math.max(run.scheduledTo, run.songStart);
    if (horizon <= from) return;
    run.scheduledTo = horizon;

    const clickBuffers = this.clickBuffers;
    if (clickBuffers && this.clickBus) {
      for (const event of eventsInWindow(this.timeline.clicks, from, horizon)) {
        const at = run.ctxStart + (event.time - run.songStart);
        if (at < now - 0.005) continue;
        this.oneShot(run, event.accent ? clickBuffers.accent : clickBuffers.normal, this.clickBus, at);
      }
    }

    const library = this.cueLibrary.get(this.state.cueLanguage);
    if (library && this.cueBus) {
      for (const cue of eventsInWindow(this.timeline.cues, from, horizon)) {
        const sample = library.get(cue.name);
        const at = run.ctxStart + (cue.time - run.songStart);
        if (!sample || at < now - 0.005) continue;
        // A cue still sounding when the next one starts is faded out there, as in the pack.
        if (run.lastCue) {
          run.lastCue.gain.setValueAtTime(1, Math.max(now, at - 0.003));
          run.lastCue.gain.linearRampToValueAtTime(0, Math.max(now, at));
        }
        const gain = ctx.createGain();
        gain.connect(this.cueBus);
        this.oneShot(run, sample.buffer, gain, at, sample.onset);
        run.lastCue = gain;
      }
    }
  };

  private oneShot(run: Run, buffer: AudioBuffer, to: AudioNode, at: number, offset = 0) {
    const ctx = this.ctx;
    if (!ctx) return;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(to);
    source.onended = () => {
      run.oneShots.delete(source);
      source.disconnect();
    };
    source.start(Math.max(at, ctx.currentTime), offset);
    run.oneShots.add(source);
  }

  /* -------------------------------------------------------------- mix */

  private applyGains() {
    const ctx = this.ctx;
    if (!ctx) return;
    const gains = stemGains(this.state.mix);
    for (const [name, node] of this.stemNodes) {
      node.gain.setTargetAtTime(gains[name], ctx.currentTime, GAIN_SMOOTHING);
    }
  }

  private setMix(name: StemName, patch: Partial<StemMix>) {
    this.set({ mix: { ...this.state.mix, [name]: { ...this.state.mix[name], ...patch } } });
    this.applyGains();
  }

  setVolume(name: StemName, volume: number) {
    this.setMix(name, { volume });
  }
  toggleMute(name: StemName) {
    this.setMix(name, { muted: !this.state.mix[name].muted });
  }
  toggleSolo(name: StemName) {
    this.setMix(name, { solo: !this.state.mix[name].solo });
  }

  /* ------------------------------------------------------ click, cues */

  setClick(on: boolean) {
    this.set({ clickOn: on });
    if (this.ctx && this.clickBus) {
      this.clickBus.gain.setTargetAtTime(on ? 1 : 0, this.ctx.currentTime, GAIN_SMOOTHING);
    }
  }

  setCues(on: boolean) {
    this.set({ cuesOn: on });
    if (this.ctx && this.cueBus) {
      this.cueBus.gain.setTargetAtTime(on ? 1 : 0, this.ctx.currentTime, GAIN_SMOOTHING);
    }
    if (on) void this.loadCues(this.state.cueLanguage);
  }

  setCueLanguage(language: CueLanguage) {
    this.set({ cueLanguage: language });
    if (this.state.cuesOn) void this.loadCues(language);
  }

  /** Fetches the language's whole cue library (a few dozen KB per cue) once. */
  private async loadCues(language: CueLanguage) {
    if (this.cueLibrary.has(language)) {
      this.set({ cuesStatus: "ready" });
      return;
    }
    const ctx = this.ensureContext();
    const token = ++this.cueToken;
    this.set({ cuesStatus: "loading" });
    try {
      const manifest = (await (await fetch(`/cues/${language}/manifest.json`)).json()) as {
        cues: Record<string, { file: string }>;
      };
      const library = new Map<SectionName, CueSample>();
      await Promise.all(
        Object.entries(manifest.cues).map(async ([name, entry]) => {
          const response = await fetch(`/cues/${language}/${entry.file}`);
          if (!response.ok) return;
          const buffer = await ctx.decodeAudioData(await response.arrayBuffer());
          const onset = leadingSilenceFrames(buffer.getChannelData(0)) / buffer.sampleRate;
          library.set(name as SectionName, { buffer, onset });
        }),
      );
      if (library.size === 0) throw new Error("empty cue library");
      this.cueLibrary.set(language, library);
      if (token === this.cueToken) this.set({ cuesStatus: "ready" });
    } catch {
      if (token === this.cueToken) this.set({ cuesStatus: "error" });
    }
  }

  /* --------------------------------------------------------- teardown */

  dispose() {
    this.loadAbort?.abort();
    this.loadAbort = null;
    this.playToken += 1;
    this.cueToken += 1;
    this.stopRun();
    this.buffers.clear();
    this.stemNodes.clear();
    this.cueLibrary.clear();
    const ctx = this.ctx;
    this.ctx = null;
    this.clickBus = null;
    this.cueBus = null;
    this.clickBuffers = null;
    if (ctx && ctx.state !== "closed") void ctx.close().catch(() => {});
    this.pausedAt = 0;
    this.state = initialState();
    for (const listener of this.listeners) listener();
  }
}
