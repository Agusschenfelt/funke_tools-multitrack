/**
 * Fetching and decoding of one stem, and the pool that runs stems three at a time. Kept free of
 * the AudioContext so the failure handling can be tested with fakes.
 */
import type { PreviewAlignment, StemName, StemSource } from "./stems";

export type LoadFailure = "expired" | "network" | "decode" | "unsupported";

export class StemLoadError extends Error {
  readonly failure: LoadFailure;
  constructor(failure: LoadFailure) {
    super(failure);
    this.failure = failure;
  }
}

/**
 * Reads a response body into a Uint8Array that owns exactly its bytes (offset 0, buffer length ==
 * byte length), so `.buffer` can go to decodeAudioData without trailing or leading garbage.
 */
export async function readBytes(
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
        chunks.push(target.slice(0, received));
        target = null;
      }
      chunks.push(value);
    }
    received += value.length;
    onProgress(received);
  }
  // A shorter body than announced must not hand over the unused tail of the preallocated buffer.
  if (target) return received === target.length ? target : target.slice(0, received);
  const joined = new Uint8Array(received);
  let at = 0;
  for (const chunk of chunks) {
    joined.set(chunk, at);
    at += chunk.length;
  }
  return joined;
}

/** An ArrayBuffer holding exactly the bytes of `bytes`, even when it is a view into a larger one. */
export function exactBuffer(bytes: Uint8Array): ArrayBuffer {
  const { buffer, byteOffset, byteLength } = bytes;
  if (byteOffset === 0 && byteLength === buffer.byteLength) return buffer as ArrayBuffer;
  return buffer.slice(byteOffset, byteOffset + byteLength) as ArrayBuffer;
}

type FetchLike = (url: string, init: { signal: AbortSignal }) => Promise<Response>;

/** Downloads a stem. 4xx means the signed link is gone; everything else is a network failure. */
export async function fetchStemBytes(
  url: string,
  signal: AbortSignal,
  onProgress: (loaded: number) => void,
  fetchImpl: FetchLike = (u, init) => fetch(u, init),
): Promise<Uint8Array> {
  try {
    const response = await fetchImpl(url, { signal });
    if (!response.ok) {
      throw new StemLoadError(response.status >= 400 && response.status < 500 ? "expired" : "network");
    }
    return await readBytes(response, onProgress);
  } catch (error) {
    if (error instanceof StemLoadError) throw error;
    throw new StemLoadError("network");
  }
}

export async function decodeStemBytes<B>(
  decode: (data: ArrayBuffer) => Promise<B>,
  bytes: Uint8Array,
): Promise<B> {
  try {
    return await decode(exactBuffer(bytes));
  } catch {
    throw new StemLoadError("decode");
  }
}

/**
 * Where a decoded preview should be cut to line up with the WAV stems. AAC starts with encoder
 * delay: decoders that honor the mp4 edit list drop it (the result is the stem's length plus at
 * most one frame of padding); the rest return it, which shows as at least `primingSamples` extra
 * frames. Only then is the head cut, so a decoder that already trimmed is never trimmed twice.
 *
 * `alignment` counts frames at the stemset's rate, but decodeAudioData resamples to the context's,
 * so `decodedRate` converts both numbers before comparing (rounded to the nearest frame).
 */
export function previewWindow(
  decodedFrames: number,
  alignment: PreviewAlignment,
  decodedRate: number = alignment.sampleRate,
): { start: number; length: number } {
  const scale = decodedRate / alignment.sampleRate;
  const samples = Math.round(alignment.samples * scale);
  const priming = Math.round(alignment.primingSamples * scale);
  const delayed = decodedFrames - samples >= priming;
  if (!delayed) return { start: 0, length: decodedFrames };
  return { start: priming, length: Math.min(samples, decodedFrames - priming) };
}

export async function pool<T>(items: readonly T[], size: number, work: (item: T) => Promise<void>) {
  let next = 0;
  const lanes = Array.from({ length: Math.min(size, items.length) }, async () => {
    while (next < items.length) await work(items[next++]);
  });
  await Promise.all(lanes);
}

/**
 * Runs `loadOne` for every source, `size` at a time. A failing stem is recorded under its own name
 * and the others carry on; nothing here rejects. Once `signal` aborts, failures are ignored
 * because they are the cancellation, not a result.
 */
export async function loadStems(
  sources: readonly StemSource[],
  size: number,
  signal: AbortSignal,
  loadOne: (source: StemSource) => Promise<void>,
  onFailure: (name: StemName, failure: LoadFailure) => void,
): Promise<Partial<Record<StemName, LoadFailure>>> {
  const failures: Partial<Record<StemName, LoadFailure>> = {};
  await pool(sources, size, async (source) => {
    if (signal.aborted) return;
    try {
      await loadOne(source);
    } catch (error) {
      if (signal.aborted) return;
      const failure = error instanceof StemLoadError ? error.failure : "network";
      failures[source.name] = failure;
      onFailure(source.name, failure);
    }
  });
  return failures;
}
