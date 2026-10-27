/** Single source of truth for the studio's help: shortcuts, gestures and the legend of small marks. */

export interface Shortcut {
  keys: readonly string[];
  /** Joins multiple keys: "or" for alternatives, "then" for a sequence, "plus" for a chord. */
  join?: "or" | "plus";
  what: string;
}

export const SHORTCUTS: readonly Shortcut[] = [
  { keys: ["Espacio"], what: "Reproducir o pausar" },
  { keys: ["L"], what: "Quitar el loop" },
  { keys: ["←", "→"], join: "or", what: "En el mapa de la canción: moverse un compás" },
  { keys: ["Re Pág", "Av Pág"], join: "or", what: "En el mapa de la canción: moverse cuatro compases" },
  { keys: ["Enter"], what: "En una sección: escucharla desde el principio" },
  { keys: ["←", "→"], join: "or", what: "En el límite entre secciones: moverlo un compás" },
  { keys: ["Ctrl", "Z"], join: "plus", what: "Deshacer un cambio de secciones (⌘ Z en Mac)" },
  { keys: ["Mayús", "Ctrl", "Z"], join: "plus", what: "Rehacer (⇧ ⌘ Z en Mac)" },
  { keys: ["?"], what: "Abrir o cerrar esta ayuda" },
];

export const GESTURES: readonly { how: string; what: string }[] = [
  { how: "Arrastrá sobre la regla", what: "Repite un tramo (Alt o Opción: sin ajustar a compases)." },
  { how: "Clic en una pista o en la regla", what: "Mueve la reproducción ahí." },
  { how: "Doble clic en una sección", what: "La escucha desde el principio." },
  { how: "Clic en una sección", what: "La elige para renombrarla, dividirla o unirla." },
];

export const AREAS: readonly { name: string; what: string }[] = [
  { name: "Secciones", what: "La forma de la canción. Elegí una para corregirla; los cambios se guardan con Guardar." },
  { name: "Mezcla", what: "Mezclas rápidas, la regla (compases o tiempo), el loop y las descargas." },
  { name: "Pistas", what: "Una por instrumento: silenciar, solo, volumen y paneo." },
  { name: "Barra de abajo", what: "Reproducir, dónde estás, click y guías habladas." },
];

export interface Legend {
  mark: string;
  mono: boolean;
  /** One word for the compact line under the lanes. */
  short: string;
  what: string;
}

export const LEGEND: readonly Legend[] = [
  { mark: "M", short: "silenciar", mono: true, what: "Silenciar esa pista." },
  { mark: "S", short: "solo", mono: true, what: "Solo: escuchar solo esa pista." },
  { mark: "L – R", short: "paneo", mono: true, what: "Paneo: izquierda a derecha. Doble clic o Enter lo centra." },
  { mark: "revisar", short: "revisar", mono: true, what: "Sección con poca confianza: revisala y corregí el nombre si hace falta." },
  { mark: "Compases con líneas punteadas", short: "grilla estimada", mono: false, what: "Grilla estimada: la intro no tiene pulso claro." },
  { mark: "Cuenta", short: "cuenta", mono: true, what: "Antes del primer compás: es la cuenta de entrada." },
];

export const HELP_TITLE = "Cómo funciona el estudio";

/** The "?" key opens the help, unless the user is typing. */
export function isHelpKey(event: { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean }): boolean {
  return event.key === "?" && !event.ctrlKey && !event.metaKey && !event.altKey;
}
