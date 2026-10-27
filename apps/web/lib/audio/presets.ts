/** Quick mixes: each one is only a mute/solo layout, so the studio can tell when it still applies. */
import type { StemMix } from "./mix";
import type { StemName } from "./stems";

export type PresetId = "original" | "karaoke" | "acapella" | "drumless" | "bassless";
export type MixPreset = PresetId | "custom";

export const PRESETS: readonly { id: PresetId; label: string }[] = [
  { id: "original", label: "Original" },
  { id: "karaoke", label: "Karaoke (sin voz)" },
  { id: "acapella", label: "Acapella (solo voz)" },
  { id: "drumless", label: "Sin batería" },
  { id: "bassless", label: "Sin bajo" },
];

export const CUSTOM_LABEL = "Personalizado";

/** Whether a preset lets this stem sound. Works for any stem set: 4 or 6, unknown names stay on. */
function sounds(id: PresetId, name: StemName): boolean {
  switch (id) {
    case "original":
      return true;
    case "karaoke":
      return name !== "vocals";
    case "acapella":
      return name === "vocals";
    case "drumless":
      return name !== "drums";
    case "bassless":
      return name !== "bass";
  }
}

/** Gain per stem for a preset: 1 where it sounds, 0 where it does not. */
export function presetGains(id: PresetId, names: readonly StemName[]): Record<StemName, number> {
  const out = {} as Record<StemName, number>;
  for (const name of names) out[name] = sounds(id, name) ? 1 : 0;
  return out;
}

/** The mute/solo state a preset sets. Solos are cleared; volume and pan are left alone. */
export function applyPresetToMix(
  id: PresetId,
  mix: Record<StemName, StemMix>,
  names: readonly StemName[],
): Record<StemName, StemMix> {
  const gains = presetGains(id, names);
  const out = { ...mix };
  for (const name of names) out[name] = { ...mix[name], muted: gains[name] === 0, solo: false };
  return out;
}

/**
 * Which preset the current mute/solo state equals; `custom` once the user changed anything else.
 * Derived, never stored: the control cannot disagree with the lanes.
 */
export function detectPreset(
  mix: Record<StemName, StemMix>,
  names: readonly StemName[],
): MixPreset {
  if (names.length === 0 || names.some((name) => mix[name].solo)) return "custom";
  const match = PRESETS.find(({ id }) => {
    const gains = presetGains(id, names);
    return names.every((name) => mix[name].muted === (gains[name] === 0));
  });
  return match?.id ?? "custom";
}
