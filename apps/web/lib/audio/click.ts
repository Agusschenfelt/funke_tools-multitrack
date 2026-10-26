/** The "classic" click, synthesized like `audio_core/click.py` (cosine, 8 ms decay, 60 ms). */
const ACCENT_PEAK = 0.708;
const NORMAL_PEAK = 0.447;

export function clickWave(accent: boolean, sampleRate: number): Float32Array {
  const frames = Math.floor(0.06 * sampleRate);
  const freq = 1500 * (accent ? 1.33 : 1);
  const wave = new Float32Array(frames);
  let peak = 0;
  for (let i = 0; i < frames; i += 1) {
    const t = i / sampleRate;
    wave[i] = Math.cos(2 * Math.PI * freq * t) * Math.exp(-t / 0.008);
    peak = Math.max(peak, Math.abs(wave[i]));
  }
  const gain = (accent ? ACCENT_PEAK : NORMAL_PEAK) / (peak || 1);
  for (let i = 0; i < frames; i += 1) wave[i] *= gain;
  return wave;
}
