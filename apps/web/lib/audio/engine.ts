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
import { clampPan, DEFAULT_MIX, stemGains, type StemMix } from "./mix";
import { applyPresetToMix, type PresetId } from "./presets";
import { inLoop, normalizeLoop, songPositionAt, windowSegments, type LoopRange } from "./loop";
import {
  encodeWav,
  guardDb,
  levelGuard,
  mixdownStems,
  peakOf,
  renderMixdown,
  type BitDepth,
} from "./mixdown";
import { bucketCount, computePeaks, type Peaks } from "./peaks";
import {
  eventsInWindow,
  leadingSilenceFrames,
  type ClickEvent,
  type CuePlacement,
} from "./schedule";
import {
  decodeStemBytes,
  fetchStemBytes,
  loadStems,
  previewWindow,
  type LoadFailure,
} from "./stemLoad";
import { STEM_ORDER, type PreviewAlignment, type StemName, type StemSource } from "./stems";

export type { LoadFailure } from "./stemLoad";

const CONTEXT_RATE = 44100;
const LOOKAHEAD = 0.3;
const TICK_MS = 25;
const START_DELAY = 0.06;
const DOWNLOADS_AT_ONCE = 3;
const GAIN_SMOOTHING = 0.01;

export type StemPhase = "pending" | "downloading" | "decoding" | "ready" | "error";
export type CueLanguage = "es" | "en";

export interface StemView {
  phase: StemPhase;
  /** Bytes received so far (the API does not expose Content-Length cross-origin). */
  loaded: number;
  peaks: Peaks | null;
  /** Why this stem failed; the other stems keep loading. */
  failure: LoadFailure | null;
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
  /** Section A-B being repeated, or null. Playback never leaves it while it is set. */
  loop: LoopRange | null;
}

export interface MixExportOptions {
  bitDepth: BitDepth;
  includeClick: boolean;
  includeCues: boolean;
  /** WAV stems to download and use instead of what the studio has loaded (full quality). */
  fullQuality?: readonly StemSource[];
  onProgress?: (progress: { phase: "download" | "mix" | "encode"; fraction: number }) => void;
  signal?: AbortSignal;
}

export interface MixExport {
  blob: Blob;
  seconds: number;
  /** dB the level guard took off to keep the summed stems from clipping; 0 when it did nothing. */
  reducedDb: number;
}

/** Why a mix could not be exported (cancelling rejects with an AbortError instead). */
export class MixExportError extends Error {
  constructor(readonly kind: "notReady" | "download" | "decode" | "cues" | "render") {
    super(`mix export failed: ${kind}`);
  }
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
  /** Song position at `ctxStart`. A live loop change moves both so the pair stays consistent. */
  songStart: number;
  /** Seconds since `ctxStart` that click and cue events were already scheduled up to. */
  scheduledElapsed: number;
  sources: AudioBufferSourceNode[];
  /** Click and cue sources that have not finished, with the context time each one starts at. */
  oneShots: Map<AudioBufferSourceNode, number>;
  lastCue: GainNode | null;
}

function emptyStems(): Record<StemName, StemView> {
  const out = {} as Record<StemName, StemView>;
  for (const name of STEM_ORDER) out[name] = { phase: "pending", loaded: 0, peaks: null, failure: null };
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
    loop: null,
  };
}

/** Cuts a decoded preview so it starts at the same sample as its WAV stem (see `previewWindow`). */
function alignPreview(ctx: AudioContext, buffer: AudioBuffer, alignment: PreviewAlignment): AudioBuffer {
  const { start, length } = previewWindow(buffer.length, alignment, buffer.sampleRate);
  if (start === 0 && length === buffer.length) return buffer;
  const aligned = ctx.createBuffer(buffer.numberOfChannels, length, buffer.sampleRate);
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    aligned.copyToChannel(buffer.getChannelData(channel).subarray(start, start + length), channel);
  }
  return aligned;
}

function stop(node: AudioBufferSourceNode) {
  try {
    node.stop();
  } catch {
    // Already stopped or never started.
  }
  node.disconnect();
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
  private readonly panNodes = new Map<StemName, StereoPannerNode>();
  private readonly buffers = new Map<StemName, AudioBuffer>();
  private readonly cueLibrary = new Map<CueLanguage, Map<SectionName, CueSample>>();

  private timeline: EngineTimeline = { beats: [], clicks: [], cues: [] };
  private run: Run | null = null;
  private pausedAt = 0;
  private timer: ReturnType<typeof setInterval> | null = null;
  private loadAbort: AbortController | null = null;
  private playToken = 0;
  private cueToken = 0;
  private disposed = false;

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
    if (this.disposed) return;
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
    this.panNodes.clear();
    return ctx;
  }

  /* ---------------------------------------------------------- loading */

  setTimeline(timeline: EngineTimeline) {
    this.timeline = timeline;
  }

  /**
   * Loads every stem. Calling it again (or while playing) first stops playback and drops the
   * previous buffers and gain nodes, so no source from the old song keeps sounding. A stem that
   * fails reports its own error and the others continue; the engine ends in `error` if any failed.
   * Never rejects.
   */
  async load(sources: readonly StemSource[], signal: AbortSignal): Promise<void> {
    if (this.disposed) return;
    this.loadAbort?.abort();
    const abort = new AbortController();
    this.loadAbort = abort;
    const onAbort = () => abort.abort();
    if (signal.aborted) abort.abort();
    else signal.addEventListener("abort", onAbort, { once: true });

    this.resetForLoad();
    let ctx: AudioContext;
    try {
      ctx = this.ensureContext();
    } catch {
      signal.removeEventListener("abort", onAbort);
      this.set({ status: "error", failure: "unsupported" });
      return;
    }
    this.set({
      status: "loading",
      failure: null,
      order: sources.map((s) => s.name),
      stems: emptyStems(),
      playing: false,
      duration: 0,
      loop: null,
    });

    try {
      const failures = await loadStems(
        sources,
        DOWNLOADS_AT_ONCE,
        abort.signal,
        (source) => this.loadStem(ctx, source, abort.signal),
        (name, failure) => this.setStem(name, { phase: "error", failure }),
      );
      if (abort.signal.aborted || this.loadAbort !== abort) return;
      const failed = sources.find((s) => failures[s.name]);
      if (failed) {
        this.set({ status: "error", failure: failures[failed.name] ?? "network" });
        return;
      }
      let duration = 0;
      for (const buffer of this.buffers.values()) duration = Math.max(duration, buffer.duration);
      this.applyGains();
      this.set({ status: "ready", duration });
    } finally {
      signal.removeEventListener("abort", onAbort);
    }
  }

  /** For callers that caught an unexpected load error: surfaces it as a visible error state. */
  reportFailure(failure: LoadFailure) {
    this.set({ status: "error", failure });
  }

  /** Stops whatever is sounding and forgets the previous song's audio graph. */
  private resetForLoad() {
    this.playToken += 1;
    this.stopRun();
    for (const node of this.stemNodes.values()) node.disconnect();
    for (const node of this.panNodes.values()) node.disconnect();
    this.stemNodes.clear();
    this.panNodes.clear();
    this.buffers.clear();
    this.pausedAt = 0;
  }

  private async loadStem(ctx: AudioContext, source: StemSource, signal: AbortSignal) {
    const { name, url, alignment } = source;
    this.setStem(name, { phase: "downloading", loaded: 0, failure: null });
    const bytes = await fetchStemBytes(url, signal, (loaded) => this.setStem(name, { loaded }));
    if (signal.aborted) return;
    this.setStem(name, { phase: "decoding" });
    let buffer = await decodeStemBytes((data) => ctx.decodeAudioData(data), bytes);
    if (signal.aborted) return;
    if (alignment) buffer = alignPreview(ctx, buffer, alignment);
    const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) =>
      buffer.getChannelData(i),
    );
    const peaks = computePeaks(channels, bucketCount(buffer.duration));
    const node = ctx.createGain();
    // Stem -> gain -> panner -> out. A browser without StereoPannerNode just plays centred.
    if (typeof ctx.createStereoPanner === "function") {
      const panner = ctx.createStereoPanner();
      panner.pan.value = this.state.mix[name].pan;
      node.connect(panner);
      panner.connect(ctx.destination);
      this.panNodes.set(name, panner);
    } else {
      node.connect(ctx.destination);
    }
    this.stemNodes.set(name, node);
    this.buffers.set(name, buffer);
    this.setStem(name, { phase: "ready", peaks });
  }

  /* --------------------------------------------------------- playback */

  getPosition(): number {
    const { run, ctx } = this;
    if (!run || !ctx) return this.pausedAt;
    const elapsed = Math.max(0, ctx.currentTime - run.ctxStart);
    return Math.min(this.state.duration, songPositionAt(run.songStart, elapsed, this.state.loop));
  }

  readonly toggle = () => {
    if (this.state.playing) this.pause();
    else void this.play();
  };

  async play(): Promise<void> {
    if (this.disposed || this.state.status !== "ready" || this.state.playing) return;
    const token = ++this.playToken;
    const ctx = this.ensureContext();
    try {
      await ctx.resume();
    } catch {
      return;
    }
    if (this.disposed || token !== this.playToken || this.state.playing) return;
    const { loop } = this.state;
    let from = this.pausedAt >= this.state.duration - 0.05 ? 0 : this.pausedAt;
    if (loop && !inLoop(loop, from)) from = loop.start;
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
    // Jumping out of the loop leaves it: the band would otherwise promise a wrap that no longer happens.
    if (this.state.loop && !inLoop(this.state.loop, target)) this.set({ loop: null });
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
      this.applyLoop(source, this.state.loop);
      source.start(ctxStart, offset);
      sources.push(source);
    }
    this.run = {
      ctxStart,
      songStart: offset,
      scheduledElapsed: 0,
      sources,
      oneShots: new Map(),
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
    for (const source of run.oneShots.keys()) stop(source);
  }

  private readonly tick = () => {
    const { run, ctx } = this;
    if (this.disposed || !run || !ctx) return;
    if (this.getPosition() >= this.state.duration) {
      this.pausedAt = this.state.duration;
      this.stopRun();
      this.set({ playing: false });
      return;
    }
    const now = ctx.currentTime;
    const from = Math.max(run.scheduledElapsed, 0);
    const to = now + LOOKAHEAD - run.ctxStart;
    if (to <= from) return;
    run.scheduledElapsed = to;

    // Each stretch is continuous song time; a wrap of the loop starts a new one, so events on
    // both sides of it land at the right moment on the context clock.
    const stretches = windowSegments(run.songStart, from, to, this.state.loop);
    const clickBuffers = this.clickBuffers;
    const library = this.cueLibrary.get(this.state.cueLanguage);
    for (const stretch of stretches) {
      const when = (time: number) => run.ctxStart + stretch.at + (time - stretch.from);
      if (clickBuffers && this.clickBus) {
        for (const event of eventsInWindow(this.timeline.clicks, stretch.from, stretch.to)) {
          const at = when(event.time);
          if (at < now - 0.005) continue;
          this.oneShot(run, event.accent ? clickBuffers.accent : clickBuffers.normal, this.clickBus, at);
        }
      }
      if (library && this.cueBus) {
        for (const cue of eventsInWindow(this.timeline.cues, stretch.from, stretch.to)) {
          const sample = library.get(cue.name);
          const at = when(cue.time);
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
    const startAt = Math.max(at, ctx.currentTime);
    source.start(startAt, offset);
    run.oneShots.set(source, startAt);
  }

  /* ------------------------------------------------------------- loop */

  private applyLoop(source: AudioBufferSourceNode, loop: LoopRange | null) {
    source.loop = loop !== null;
    if (loop) {
      source.loopStart = loop.start;
      source.loopEnd = loop.end;
    }
  }

  /**
   * Repeats `range` (null clears it). The stems wrap natively inside their buffers, which is
   * sample-accurate; clicks and cues are scheduled across the wrap by `windowSegments`. While
   * playing, a range that contains the playhead takes effect without a gap; one that does not
   * moves the playhead to its start. Paused, the playhead moves there so Play starts the loop.
   */
  setLoop(range: LoopRange | null) {
    if (this.disposed) return;
    const next = range ? normalizeLoop(range, this.state.duration) : null;
    const { run, ctx } = this;
    const position = run && ctx ? this.getPosition() : this.pausedAt;
    this.set({ loop: next });
    if (!run || !ctx) {
      if (next && !inLoop(next, position)) this.pausedAt = next.start;
      return;
    }
    if (next && !inLoop(next, position)) {
      this.stopRun();
      this.startRun(ctx, next.start);
      return;
    }
    const now = ctx.currentTime;
    // Events scheduled ahead assumed the old wrap; drop the ones not yet sounding and schedule again.
    for (const [source, startsAt] of run.oneShots) {
      if (startsAt > now) {
        stop(source);
        run.oneShots.delete(source);
      }
    }
    if (now >= run.ctxStart) {
      run.songStart = position;
      run.ctxStart = now;
    }
    run.scheduledElapsed = 0;
    for (const source of run.sources) this.applyLoop(source, next);
    this.tick();
  }

  clearLoop() {
    this.setLoop(null);
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

  private applyPans() {
    const ctx = this.ctx;
    if (!ctx) return;
    for (const [name, node] of this.panNodes) {
      node.pan.setTargetAtTime(this.state.mix[name].pan, ctx.currentTime, GAIN_SMOOTHING);
    }
  }

  private setMix(name: StemName, patch: Partial<StemMix>) {
    this.set({ mix: { ...this.state.mix, [name]: { ...this.state.mix[name], ...patch } } });
    this.applyGains();
  }

  setPan(name: StemName, pan: number) {
    this.set({ mix: { ...this.state.mix, [name]: { ...this.state.mix[name], pan: clampPan(pan) } } });
    this.applyPans();
  }

  /** Sets remembered pans in one go (before they were loaded the lanes were centred). */
  restorePans(pans: Partial<Record<StemName, number>>) {
    const mix = { ...this.state.mix };
    for (const name of STEM_ORDER) {
      const pan = pans[name];
      if (pan !== undefined) mix[name] = { ...mix[name], pan: clampPan(pan) };
    }
    this.set({ mix });
    this.applyPans();
  }

  /** Replaces the mute/solo layout with a quick mix; volume and pan stay. */
  applyPreset(id: PresetId) {
    this.set({ mix: applyPresetToMix(id, this.state.mix, this.state.order) });
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

  /* ----------------------------------------------------------- export */

  /**
   * Renders the current mix (gains, mutes, solos, pans; no loop) offline into a WAV. Uses the
   * loaded buffers, or downloads `fullQuality` sources first when the studio holds previews.
   */
  async exportMix(options: MixExportOptions): Promise<MixExport> {
    const { bitDepth, signal } = options;
    const report = options.onProgress ?? (() => {});
    const aborted = () => new DOMException("Export cancelled", "AbortError");
    if (this.disposed || this.state.status !== "ready") throw new MixExportError("notReady");
    const ctx = this.ensureContext();
    const abort = signal ?? new AbortController().signal;

    let source: ReadonlyMap<StemName, AudioBuffer> = this.buffers;
    if (options.fullQuality?.length) {
      const full = new Map<StemName, AudioBuffer>();
      let done = 0;
      report({ phase: "download", fraction: 0 });
      for (const wav of options.fullQuality) {
        if (abort.aborted) throw aborted();
        try {
          const bytes = await fetchStemBytes(wav.url, abort, () => {});
          full.set(wav.name, await decodeStemBytes((data) => ctx.decodeAudioData(data), bytes));
        } catch (error) {
          if (abort.aborted) throw aborted();
          const failure = (error as { failure?: LoadFailure }).failure;
          throw new MixExportError(failure === "decode" ? "decode" : "download");
        }
        done += 1;
        report({ phase: "download", fraction: done / options.fullQuality.length });
      }
      source = full;
    }
    if (abort.aborted) throw aborted();

    const stems = mixdownStems(this.state.order, this.state.mix, source);
    let frames = 0;
    for (const buffer of source.values()) frames = Math.max(frames, buffer.length);
    const sampleRate = source.values().next().value?.sampleRate ?? ctx.sampleRate;

    let cues: Parameters<typeof renderMixdown>[0]["cues"];
    if (options.includeCues && this.timeline.cues.length > 0) {
      await this.loadCues(this.state.cueLanguage);
      const library = this.cueLibrary.get(this.state.cueLanguage);
      if (!library) throw new MixExportError("cues");
      cues = { library, placements: this.timeline.cues };
    }
    const click =
      options.includeClick && this.clickBuffers
        ? { buffers: this.clickBuffers, events: this.timeline.clicks }
        : undefined;

    let rendered: Awaited<ReturnType<typeof renderMixdown>>;
    try {
      rendered = await renderMixdown({
        stems,
        length: frames,
        sampleRate,
        click,
        cues,
        signal: abort,
        onProgress: (fraction) => report({ phase: "mix", fraction }),
      });
    } catch (error) {
      if (abort.aborted || (error as { name?: string }).name === "AbortError") throw aborted();
      throw new MixExportError("render");
    }

    report({ phase: "encode", fraction: 0 });
    const scale = levelGuard(peakOf(rendered.channels));
    const wav = encodeWav(rendered.channels, rendered.sampleRate, bitDepth, scale);
    report({ phase: "encode", fraction: 1 });
    return {
      blob: new Blob([wav], { type: "audio/wav" }),
      seconds: frames / rendered.sampleRate,
      reducedDb: guardDb(scale),
    };
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
    if (this.disposed) return;
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

  /** Final: every later call is a no-op. Create a new engine per mount instead of reusing one. */
  dispose() {
    this.disposed = true;
    this.loadAbort?.abort();
    this.loadAbort = null;
    this.playToken += 1;
    this.cueToken += 1;
    this.stopRun();
    this.buffers.clear();
    this.stemNodes.clear();
    this.panNodes.clear();
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
