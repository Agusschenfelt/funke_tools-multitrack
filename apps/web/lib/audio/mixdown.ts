/**
 * "Exportar mi mezcla": renders the studio's current mix offline and encodes it as WAV.
 *
 * The render uses an OfflineAudioContext with the same graph as playback (stem -> gain -> pan),
 * optionally with the click and the spoken cues scheduled over it. Mute/solo/volume/pan come from
 * the engine's mix; the loop is ignored, so the file is the whole song. The pure parts (which
 * stems sound and how loud, the level guard, the WAV bytes, the file name) are exported on their
 * own so they can be tested without audio.
 */
import type { SectionName } from "@/lib/api";
import { clampPan, stemGains, type StemMix } from "./mix";
import type { ClickEvent, CuePlacement } from "./schedule";
import type { StemName } from "./stems";

export type BitDepth = 16 | 24;

export const CHANNELS = 2;

export interface MixdownStem<B = AudioBuffer> {
  name: StemName;
  buffer: B;
  gain: number;
  pan: number;
}

/** The stems that make sound in this mix, with the gain and pan the lanes show. Silent ones are left out. */
export function mixdownStems<B>(
  order: readonly StemName[],
  mix: Record<StemName, StemMix>,
  buffers: ReadonlyMap<StemName, B>,
): MixdownStem<B>[] {
  const gains = stemGains(mix);
  const out: MixdownStem<B>[] = [];
  for (const name of order) {
    const buffer = buffers.get(name);
    if (buffer === undefined || !(gains[name] > 0)) continue;
    out.push({ name, buffer, gain: gains[name], pan: clampPan(mix[name].pan) });
  }
  return out;
}

/** Highest absolute sample across channels. */
export function peakOf(channels: readonly Float32Array[]): number {
  let peak = 0;
  for (const channel of channels) {
    for (let i = 0; i < channel.length; i += 1) {
      const value = Math.abs(channel[i]);
      if (value > peak) peak = value;
    }
  }
  return peak;
}

/** Gain that keeps a summed mix from clipping: 1 when it already fits, otherwise 1 / peak. */
export function levelGuard(peak: number): number {
  return peak > 1 ? 1 / peak : 1;
}

/** How much quieter the guard made the mix, in dB (a positive number); 0 when it did nothing. */
export function guardDb(scale: number): number {
  return scale >= 1 ? 0 : -20 * Math.log10(scale);
}

/** Bytes of the WAV file for a stereo render. */
export function wavSize(frames: number, bitDepth: BitDepth): number {
  return 44 + frames * CHANNELS * (bitDepth / 8);
}

/**
 * Little-endian PCM WAV (RIFF) from channel data, scaled by `scale` and hard-limited to full
 * scale. 16-bit and 24-bit are integer PCM; mono input is written as mono.
 */
export function encodeWav(
  channels: readonly Float32Array[],
  sampleRate: number,
  bitDepth: BitDepth,
  scale = 1,
): ArrayBuffer {
  const count = channels.length;
  const frames = count === 0 ? 0 : channels[0].length;
  const bytes = bitDepth / 8;
  const dataSize = frames * count * bytes;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, count, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * count * bytes, true);
  view.setUint16(32, count * bytes, true);
  view.setUint16(34, bitDepth, true);
  text(36, "data");
  view.setUint32(40, dataSize, true);

  const full = 2 ** (bitDepth - 1);
  let offset = 44;
  for (let i = 0; i < frames; i += 1) {
    for (let c = 0; c < count; c += 1) {
      const value = Math.max(-1, Math.min(1, channels[c][i] * scale));
      const int = Math.max(-full, Math.min(full - 1, Math.round(value * full)));
      if (bitDepth === 16) {
        view.setInt16(offset, int, true);
      } else {
        view.setUint8(offset, int & 0xff);
        view.setUint8(offset + 1, (int >> 8) & 0xff);
        view.setUint8(offset + 2, (int >> 16) & 0xff);
      }
      offset += bytes;
    }
  }
  return buffer;
}

/** `<title> - mezcla.wav`, without characters a file system rejects. */
export function mixFilename(title: string): string {
  const clean = title
    .replace(/[\u0000-\u001f<>:"/\\|?*]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[\s.]+|[\s.]+$/g, "");
  return `${clean || "Mi tema"} - mezcla.wav`;
}

/* ------------------------------------------------------------ render */

interface CueSample {
  buffer: AudioBuffer;
  onset: number;
}

export interface MixdownJob {
  stems: readonly MixdownStem[];
  /** Frames to render; at least the longest stem. */
  length: number;
  sampleRate: number;
  click?: { buffers: { accent: AudioBuffer; normal: AudioBuffer }; events: readonly ClickEvent[] };
  cues?: { library: ReadonlyMap<SectionName, CueSample>; placements: readonly CuePlacement[] };
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
  createContext?: (channels: number, length: number, sampleRate: number) => OfflineAudioContext;
}

export interface Rendered {
  channels: Float32Array[];
  sampleRate: number;
}

/** Seconds of audio between progress reports. */
const PROGRESS_SECONDS = 4;
/** Web Audio renders in blocks of this many frames; suspend points must sit on a block edge. */
const QUANTUM = 128;

function abortError() {
  return new DOMException("Export cancelled", "AbortError");
}

export async function renderMixdown(job: MixdownJob): Promise<Rendered> {
  const { stems, length, sampleRate, signal } = job;
  if (signal?.aborted) throw abortError();
  const make =
    job.createContext ?? ((c, l, r) => new OfflineAudioContext(c, l, r));
  const ctx = make(CHANNELS, Math.max(1, length), sampleRate);

  for (const stem of stems) {
    const source = ctx.createBufferSource();
    source.buffer = stem.buffer;
    const gain = ctx.createGain();
    gain.gain.value = stem.gain;
    source.connect(gain);
    if (typeof ctx.createStereoPanner === "function") {
      const panner = ctx.createStereoPanner();
      panner.pan.value = stem.pan;
      gain.connect(panner);
      panner.connect(ctx.destination);
    } else {
      gain.connect(ctx.destination);
    }
    source.start(0);
  }

  if (job.click) {
    for (const event of job.click.events) {
      const source = ctx.createBufferSource();
      source.buffer = event.accent ? job.click.buffers.accent : job.click.buffers.normal;
      source.connect(ctx.destination);
      source.start(Math.max(0, event.time));
    }
  }

  if (job.cues) {
    const { library, placements } = job.cues;
    let previous: GainNode | null = null;
    for (const cue of placements) {
      const sample = library.get(cue.name);
      if (!sample) continue;
      // As on stage: a cue still sounding when the next one starts is faded out there.
      if (previous) {
        previous.gain.setValueAtTime(1, Math.max(0, cue.time - 0.003));
        previous.gain.linearRampToValueAtTime(0, Math.max(0, cue.time));
      }
      const gain = ctx.createGain();
      gain.connect(ctx.destination);
      const source = ctx.createBufferSource();
      source.buffer = sample.buffer;
      source.connect(gain);
      source.start(Math.max(0, cue.time), sample.onset);
      previous = gain;
    }
  }

  // A render cannot report progress by itself; pausing it at regular points can.
  const progress = job.onProgress;
  if (progress) {
    const step = Math.max(QUANTUM, Math.floor((PROGRESS_SECONDS * sampleRate) / QUANTUM) * QUANTUM);
    for (let frame = step; frame < length - QUANTUM; frame += step) {
      void ctx
        .suspend(frame / sampleRate)
        .then(() => {
          progress(frame / length);
          return ctx.resume();
        })
        .catch(() => {});
    }
  }

  const rendered = await ctx.startRendering();
  if (signal?.aborted) throw abortError();
  progress?.(1);
  return {
    channels: Array.from({ length: rendered.numberOfChannels }, (_, i) => rendered.getChannelData(i)),
    sampleRate: rendered.sampleRate,
  };
}
