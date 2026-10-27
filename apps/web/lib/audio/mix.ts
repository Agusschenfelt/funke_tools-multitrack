export interface StemMix {
  /** 0..1 */
  volume: number;
  muted: boolean;
  solo: boolean;
  /** -1 (left) .. 1 (right); 0 is centre. */
  pan: number;
}

export const DEFAULT_MIX: StemMix = { volume: 1, muted: false, solo: false, pan: 0 };

export const clampPan = (value: number) =>
  Math.min(1, Math.max(-1, Number.isFinite(value) ? value : 0));

/** Spoken value of a pan position for assistive technology and tooltips. */
export function panText(pan: number): string {
  const percent = Math.round(Math.abs(clampPan(pan)) * 100);
  if (percent === 0) return "Centro";
  return `${percent} % ${pan < 0 ? "izquierda" : "derecha"}`;
}

const clamp01 = (value: number) => Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));

/**
 * Gain per stem. With any solo on, only soloed stems sound (solo overrides mute: soloing a stem
 * means "let me hear this"); otherwise a stem sounds unless muted. Volume scales what sounds.
 */
export function stemGains<K extends string>(mix: Record<K, StemMix>): Record<K, number> {
  const keys = Object.keys(mix) as K[];
  const anySolo = keys.some((key) => mix[key].solo);
  const out = {} as Record<K, number>;
  for (const key of keys) {
    const stem = mix[key];
    const audible = anySolo ? stem.solo : !stem.muted;
    out[key] = audible ? clamp01(stem.volume) : 0;
  }
  return out;
}
