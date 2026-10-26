export interface StemMix {
  /** 0..1 */
  volume: number;
  muted: boolean;
  solo: boolean;
}

export const DEFAULT_MIX: StemMix = { volume: 1, muted: false, solo: false };

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
