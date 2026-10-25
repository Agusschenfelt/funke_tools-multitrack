"""Generate the spoken cue library (assets/cues/<lang>/) with Piper TTS.

Run in an isolated environment; Piper is NOT a dependency of packages/audio-core:

    uv run --with piper-tts --with soundfile --with numpy --with soxr \
        python -I scripts/generate_cues.py --voices-dir <dir with .onnx + .onnx.json> --out-dir assets/cues

Voices are downloaded separately from https://huggingface.co/rhasspy/piper-voices (see assets/cues/README.md).
The manifest written here is the single source of truth for cue provenance and licenses.
"""

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr
from piper import PiperVoice, SynthesisConfig

SAMPLE_RATE = 44100
TAIL_SECONDS = 0.005
COUNT_SCALE = 0.8  # counts are spoken faster still so they fit one beat at high tempos
PEAK_DBFS = -1.0
HF = "https://huggingface.co/rhasspy/piper-voices/tree/main"

CUE_IDS = (
    "intro", "verse", "verse_2", "pre_chorus", "chorus", "bridge", "solo",
    "instrumental", "break", "outro", "tag", "count_1", "count_2", "count_3", "count_4",
)  # fmt: skip

VOICES = {
    "es": {
        "voice": "es_MX-ald-medium",
        "length_scale": 0.65,  # this voice speaks slowly; counts must fit one beat at 180 BPM
        "path": "es/es_MX/ald/medium",
        "license": "Unlicense (http://unlicense.org)",
        "dataset": "https://huggingface.co/datasets/rmcpantoja/Ald_Mexican_Spanish_speech_dataset",
        "phrases": ["Intro", "Verso", "Verso dos", "Pre coro", "Coro", "Puente", "Solo",
                    "Instrumental", "Break", "Final", "Tag", "Uno", "Dos", "Tres", "Cuatro"],
    },
    "en": {
        "voice": "en_US-ljspeech-high",
        "length_scale": 0.9,
        "path": "en/en_US/ljspeech/high",
        "license": "Public domain (LJ Speech dataset)",
        "dataset": "https://keithito.com/LJ-Speech-Dataset/",
        "phrases": ["Intro", "Verse", "Verse two", "Pre chorus", "Chorus", "Bridge", "Solo",
                    "Instrumental", "Break", "Outro", "Tag", "One", "Two", "Three", "Four"],
    },
}  # fmt: skip


def process(audio: np.ndarray, rate: int) -> np.ndarray:
    """Mono float at 44.1 kHz, silence trimmed (5 ms tail kept), peak at -1 dBFS."""
    if rate != SAMPLE_RATE:
        audio = soxr.resample(audio, rate, SAMPLE_RATE)
    peak = float(np.max(np.abs(audio)))
    loud = np.flatnonzero(np.abs(audio) >= peak * 0.01)  # -40 dB relative to peak
    audio = audio[loud[0] : loud[-1] + 1 + round(TAIL_SECONDS * SAMPLE_RATE)]
    return (audio * (10 ** (PEAK_DBFS / 20) / np.max(np.abs(audio)))).astype(np.float32)


def generate(lang: str, voices_dir: Path, out_dir: Path) -> None:
    spec = VOICES[lang]
    model = voices_dir / f"{spec['voice']}.onnx"
    voice = PiperVoice.load(model)
    model_url = f"{HF}/{spec['path']}"
    generator = f"piper-tts {version('piper-tts')}"
    lang_dir = out_dir / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    cues = {}
    for cue_id, phrase in zip(CUE_IDS, spec["phrases"], strict=True):
        chunks = voice.synthesize(phrase, SynthesisConfig(length_scale=spec["length_scale"] * (COUNT_SCALE if cue_id.startswith("count_") else 1.0)))
        parts = [(c.audio_float_array, c.sample_rate) for c in chunks]
        audio = process(np.concatenate([p[0] for p in parts]), parts[0][1])
        sf.write(lang_dir / f"{cue_id}.wav", audio, SAMPLE_RATE, subtype="PCM_24")
        print(f"{lang} {cue_id:13s} {phrase!r:16} {len(audio) / SAMPLE_RATE * 1000:6.0f} ms")
        cues[cue_id] = {
            "file": f"{cue_id}.wav",
            "license": spec["license"],
            "source": f"Piper voice {spec['voice']} ({model_url}); dataset {spec['dataset']}; "
            f"text {phrase!r}; generated with {generator}",
        }
    manifest = {
        "language": lang,
        "voice": {
            "name": spec["voice"],
            "engine": generator,
            "model_url": model_url,
            "dataset": spec["dataset"],
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "length_scale": spec["length_scale"],
            "count_length_scale": spec["length_scale"] * COUNT_SCALE,
            "format": f"mono {SAMPLE_RATE} Hz 24-bit WAV, peak {PEAK_DBFS} dBFS",
            "note": "Placeholder voice; a recorded Rioplatense voice is planned.",
        },
        "cues": cues,
    }
    (lang_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--voices-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("assets/cues"))
    parser.add_argument("--lang", choices=sorted(VOICES), action="append")
    args = parser.parse_args()
    for lang in args.lang or sorted(VOICES):
        generate(lang, args.voices_dir, args.out_dir)


if __name__ == "__main__":
    main()
