/**
 * Client-side upload rules. They mirror the API (`apps/api/api/config.py`):
 * ALLOWED_EXTENSIONS default and MAX_UPLOAD_MB default. The server stays the authority
 * and its 415/413/400 answers are mapped in `lib/api.ts`.
 */
export const ALLOWED_EXTENSIONS = [
  ".wav",
  ".mp3",
  ".flac",
  ".m4a",
  ".aac",
  ".ogg",
  ".aif",
  ".aiff",
] as const;

export const ACCEPT = ALLOWED_EXTENSIONS.join(",");

const configuredMax = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB);
export const MAX_UPLOAD_MB = configuredMax > 0 ? configuredMax : 100;

export function formatsLabel(): string {
  return ALLOWED_EXTENSIONS.map((ext) => ext.slice(1).toUpperCase()).join(", ");
}

export function unsupportedTypeMessage(): string {
  return `Ese formato no se puede procesar. Subí un archivo ${formatsLabel()}.`;
}

export function tooLargeMessage(maxMb: number = MAX_UPLOAD_MB): string {
  return `El archivo supera el límite de ${maxMb} MB. Probá con una versión más liviana.`;
}

export function emptyFileMessage(): string {
  return "El archivo está vacío o no tiene un nombre válido. Elegí otro.";
}

export type FileValidation =
  | { ok: true }
  | { ok: false; code: "extension" | "size" | "empty"; message: string };

export function extensionOf(filename: string): string {
  const name = filename.replace(/\\/g, "/").split("/").pop() ?? "";
  const dot = name.lastIndexOf(".");
  // Like Python's Path.suffix: a leading dot alone is not an extension.
  return dot > 0 ? name.slice(dot).toLowerCase() : "";
}

export function validateFile(
  file: { name: string; size: number },
  maxMb: number = MAX_UPLOAD_MB,
): FileValidation {
  const extension = extensionOf(file.name);
  if (!(ALLOWED_EXTENSIONS as readonly string[]).includes(extension)) {
    return { ok: false, code: "extension", message: unsupportedTypeMessage() };
  }
  if (file.size === 0) {
    return { ok: false, code: "empty", message: emptyFileMessage() };
  }
  if (file.size > maxMb * 1024 * 1024) {
    return { ok: false, code: "size", message: tooLargeMessage(maxMb) };
  }
  return { ok: true };
}

/** Longest accepted song. Mirrors `MAX_DURATION_SECONDS` in audio-core; the worker enforces it. */
export const MAX_DURATION_SECONDS = 600;
const METADATA_TIMEOUT_MS = 5000;

function mmss(seconds: number): string {
  const total = Math.floor(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function tooLongMessage(seconds: number): string {
  return `Este tema dura ${mmss(seconds)}. El máximo es 10 minutos.`;
}

export type DurationCheck = { ok: true } | { ok: false; code: "duration"; message: string };

/** `null` means the browser could not read the duration: the server decides then. */
export function checkDuration(
  seconds: number | null,
  maxSeconds: number = MAX_DURATION_SECONDS,
): DurationCheck {
  if (seconds === null || !Number.isFinite(seconds)) return { ok: true };
  // Same tolerance as the worker (0.5 s) so a borderline 10:00 file is not blocked here.
  if (seconds > maxSeconds + 0.5) return { ok: false, code: "duration", message: tooLongMessage(seconds) };
  return { ok: true };
}

/**
 * Duration from the file's metadata only (no decoding). Resolves `null` when the browser cannot
 * read it (unsupported format, error, or no answer within 5 s).
 */
export function readDuration(file: Blob, timeoutMs: number = METADATA_TIMEOUT_MS): Promise<number | null> {
  return new Promise((resolve) => {
    let url: string;
    try {
      url = URL.createObjectURL(file);
    } catch {
      resolve(null);
      return;
    }
    const audio = new Audio();
    const finish = (value: number | null) => {
      clearTimeout(timer);
      audio.removeAttribute("src");
      audio.load();
      URL.revokeObjectURL(url);
      resolve(value);
    };
    audio.preload = "metadata";
    audio.onloadedmetadata = () =>
      finish(Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : null);
    audio.onerror = () => finish(null);
    const timer = setTimeout(() => finish(null), timeoutMs);
    audio.src = url;
  });
}
