/** Click sounds synthesized like `audio_core/click.py` (60 ms, accent higher pitched). */
const ACCENT_PEAK = 0.708;
const NORMAL_PEAK = 0.447;

export type ClickSound = "classic" | "cowbell" | "woodblock" | "rimshot";

/** Deterministic noise for the rimshot. The server uses numpy's generator, so this is close, not identical. */
function noise(): () => number {
  let seed = 7;
  return () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return (seed / 0x80000000) - 1;
  };
}

function sample(sound: ClickSound, accent: boolean, t: number, rand: () => number): number {
  const pitch = accent ? 1.33 : 1;
  const tone = (freq: number) => Math.cos(2 * Math.PI * freq * pitch * t);
  const decay = (ms: number) => Math.exp(-t / (ms / 1000));
  switch (sound) {
    case "cowbell":
      return (Math.sign(tone(560)) + Math.sign(tone(845))) * decay(14);
    case "woodblock":
      return (tone(1100) + 0.4 * tone(2640)) * decay(6);
    case "rimshot":
      return 0.7 * rand() * decay(3) + tone(1700) * decay(10);
    default:
      return tone(1500) * decay(8);
  }
}

export function clickWave(
  accent: boolean,
  sampleRate: number,
  sound: ClickSound = "classic",
): Float32Array {
  const frames = Math.floor(0.06 * sampleRate);
  const wave = new Float32Array(frames);
  const rand = noise();
  let peak = 0;
  for (let i = 0; i < frames; i += 1) {
    wave[i] = sample(sound, accent, i / sampleRate, rand);
    peak = Math.max(peak, Math.abs(wave[i]));
  }
  const gain = (accent ? ACCENT_PEAK : NORMAL_PEAK) / (peak || 1);
  for (let i = 0; i < frames; i += 1) wave[i] *= gain;
  return wave;
}
