/** File size in the es-AR convention: decimal comma, binary units. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const text = value.toLocaleString("es-AR", { maximumFractionDigits: value >= 100 ? 0 : 1 });
  return `${text} ${units[unit]}`;
}
