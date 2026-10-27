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
