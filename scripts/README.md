# Scripts

## Section detection evaluation

`eval_sections.py` compares the sections detected by `audio_core` with hand-made annotations and reports
boundary hit rate and per-bar label accuracy. Run it from the repository root:

```sh
uv run --project packages/audio-core python scripts/eval_sections.py <songs dir> --out <report dir>
```

It prints a per-song table with macro averages and writes `eval_report.json` (sections model version,
date, per-song metrics, macro average) to `--out` (default: the songs directory). A song that fails is
listed with its error and the exit code is 1; the other songs are still scored.

### Songs directory layout

Per song, with the same `<name>`:

| File | Required | Content |
| --- | --- | --- |
| `<name>.<ext>` | yes | Audio (`wav`, `mp3`, `flac`, `m4a`, `ogg`, `aiff`). |
| `<name>.sections.json` | yes | The annotation (below). |
| `<name>.analysis.json` | no | `analyze` output to reuse; otherwise the song is analyzed. |
| `<name>.stems/` | no | A stem set directory (`stemset.json` + WAVs); its vocals stem is used for detection. |

### Annotating a song

The annotation uses the same schema as a `sections.json` for `stagepack --sections`:

```json
{
  "sections": [
    {"name": "intro", "start": 0.0},
    {"name": "verse", "start": 8.0},
    {"name": "chorus", "start": 40.0}
  ]
}
```

- `start` is in seconds from the start of the original audio, sorted and unique.
- `name` is one of: `intro`, `verse`, `verse_2`, `pre_chorus`, `chorus`, `bridge`, `solo`,
  `instrumental`, `break`, `outro`, `tag`.
- Mark the start of each section at its first downbeat (the "1" of the first bar). Detected starts are
  always downbeats, so an annotation placed on a pickup or a fill is penalized at 0.5 s tolerance.
- Use `verse_2` for the second and later verses. The relaxed accuracy treats it as `verse`.
- List the first section at the song start (usually `0.0`); the song start itself is never scored as a
  boundary.
- A tempo-aware audio editor with a bar grid makes this much faster; `audio-core analyze` prints the BPM
  and writes the downbeat times to `analysis.json`.

### Metrics

- Boundary hit rate at 0.5 s and 3 s (HR.5F and HR3F): precision, recall and F with one-to-one
  matching. The first section start of each side is excluded.
- Label accuracy: the fraction of bars whose detected label equals the annotated label, using the
  section that contains each bar's midpoint. The relaxed version maps `verse_2` to `verse`.
- Macro average: the unweighted mean over songs.

### Licensing

Only commit songs the project may legally redistribute: public domain (CC0), CC BY, or owned by the
agency. Real songs normally stay out of the repository; keep them in a local directory and pass its path
to the script. Annotations of songs you cannot redistribute can still be committed only if they carry
no audio and the license of the source allows it.
