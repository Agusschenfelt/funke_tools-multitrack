/** Waveform peaks: computed once per stem at a fixed resolution, then re-bucketed per pixel. */

export interface Peaks {
  /** Interleaved min, max per bucket, in -1..1. */
  data: Float32Array;
  /** Multiplier that fills the lane: 1 / loudest peak, capped so a near-silent stem stays quiet. */
  scale: number;
}

const MAX_SCALE = 20;

export function bucketCount(durationSeconds: number): number {
  return Math.min(16384, Math.max(2048, Math.ceil(durationSeconds * 25)));
}

/** Min/max of the channel mean per bucket. Reads the channels in place; allocates only the result. */
export function computePeaks(channels: readonly Float32Array[], buckets: number): Peaks {
  const length = channels[0]?.length ?? 0;
  const data = new Float32Array(buckets * 2);
  const n = channels.length;
  let loudest = 0;
  for (let b = 0; b < buckets; b += 1) {
    const from = Math.floor((b * length) / buckets);
    const to = Math.max(from + 1, Math.floor(((b + 1) * length) / buckets));
    let min = Infinity;
    let max = -Infinity;
    for (let i = from; i < to && i < length; i += 1) {
      let sum = 0;
      for (let c = 0; c < n; c += 1) sum += channels[c][i];
      const v = sum / n;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    if (min === Infinity) {
      min = 0;
      max = 0;
    }
    data[b * 2] = min;
    data[b * 2 + 1] = max;
    loudest = Math.max(loudest, -min, max);
  }
  return { data, scale: Math.min(MAX_SCALE, 1 / Math.max(loudest, 1e-6)) };
}

/** Fold (or stretch) peaks to exactly `width` interleaved min/max columns. */
export function rebucket(peaks: Float32Array, width: number): Float32Array {
  const source = peaks.length / 2;
  const out = new Float32Array(width * 2);
  if (source === 0 || width <= 0) return out;
  for (let x = 0; x < width; x += 1) {
    const from = Math.floor((x * source) / width);
    const to = Math.max(from + 1, Math.ceil(((x + 1) * source) / width));
    let min = Infinity;
    let max = -Infinity;
    for (let i = from; i < to && i < source; i += 1) {
      if (peaks[i * 2] < min) min = peaks[i * 2];
      if (peaks[i * 2 + 1] > max) max = peaks[i * 2 + 1];
    }
    out[x * 2] = min === Infinity ? 0 : min;
    out[x * 2 + 1] = max === -Infinity ? 0 : max;
  }
  return out;
}
