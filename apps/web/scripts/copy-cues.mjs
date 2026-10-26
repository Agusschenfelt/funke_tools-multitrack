// Copies the spoken-cue library (assets/cues/<lang>) into public/cues so the browser can fetch the
// same WAVs the server uses for the pack. Runs before dev and build; the copy is git-ignored.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "..", "..", "assets", "cues");
const target = join(root, "public", "cues");

if (!existsSync(source)) {
  console.error(`copy-cues: ${source} not found; spoken cues will be unavailable.`);
  process.exit(0);
}

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
for (const language of ["es", "en"]) {
  const from = join(source, language);
  if (!existsSync(from)) continue;
  cpSync(from, join(target, language), {
    recursive: true,
    filter: (path) => !path.endsWith(".gitkeep"),
  });
}
console.log("copy-cues: assets/cues -> public/cues");
