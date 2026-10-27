# Spoken cue samples

Guide-track cues (section names and the 1-4 count) used by `audio_core.guide`. Each language is a
directory with a `manifest.json` (the single source of truth for files, licenses and sources) and one
`<cue_id>.wav` per cue: mono, 44.1 kHz, 24-bit, silence trimmed, peak at -1 dBFS.

| Language | Voice | License | Source |
| --- | --- | --- | --- |
| `es` | Piper `es_MX-ald-medium` | Unlicense (model card and dataset card) | https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_MX/ald/medium, dataset https://huggingface.co/datasets/rmcpantoja/Ald_Mexican_Spanish_speech_dataset |
| `en` | Piper `en_US-ljspeech-high` | Public domain (LJ Speech) | https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ljspeech/high, dataset https://keithito.com/LJ-Speech-Dataset/ |

The WAV files are generated output; their terms follow the voice and dataset licenses above. The Piper
engine itself is GPL-3.0 but is only used at generation time and is not shipped or imported by the app.

These are placeholders: a recorded Rioplatense Spanish voice is planned and will replace the Spanish set.
Because the manifest is the source of truth, swapping voices means replacing the WAVs and updating it.

## Regenerate

Download the `.onnx` and `.onnx.json` of each voice from the model URLs above into an empty directory
outside the repository, then from the repository root:

```sh
uv run --no-project --with piper-tts --with soundfile --with numpy --with soxr \
  python -I scripts/generate_cues.py --voices-dir /path/to/voices --out-dir assets/cues
```

Counts are synthesized faster than section names so they fit one beat at high tempos (see
`count_length_scale` in each manifest). Re-verify licenses before changing voices.
