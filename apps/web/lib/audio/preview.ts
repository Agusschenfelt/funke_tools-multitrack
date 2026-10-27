import { clickWave, type ClickSound } from "./click";

let context: AudioContext | null = null;

/** Plays an accent and two normal clicks of one sound (for choosing it). Returns false if audio is unavailable. */
export async function playClickPreview(sound: ClickSound): Promise<boolean> {
  try {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return false;
    context ??= new Ctor();
    const ctx = context;
    if (ctx.state === "suspended") await ctx.resume();
    const start = ctx.currentTime + 0.05;
    [true, false, false].forEach((accent, i) => {
      const wave = clickWave(accent, ctx.sampleRate, sound);
      const buffer = ctx.createBuffer(1, wave.length, ctx.sampleRate);
      buffer.copyToChannel(wave as Float32Array<ArrayBuffer>, 0);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      source.start(start + i * 0.3);
    });
    return true;
  } catch {
    return false;
  }
}
