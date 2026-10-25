"""Stage Pack assembly: sample-aligned WAVs, tempo map, section list and import notes in a ZIP.

Everything is built at the internal 44.1 kHz float32 rate. The only conversions happen at export:
soxr resampling when the destination rate is 48 kHz, then 24-bit PCM. Every exported WAV has the
same frame count, computed once from the internal pack length.

Pack length: ``pad_samples + original samples``. No extra tail is added, so the pack ends exactly
where the song ends and a click or cue that would fall past the end is cut (never wrapped).
"""

import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import mido
import numpy as np
import soundfile as sf
import soxr
from pydantic import ValidationError

from audio_core.click import click_events, render_click
from audio_core.constants import DTYPE, SAMPLE_RATE
from audio_core.guide import (
    CueLibrary,
    CueLibraryError,
    default_library_dir,
    render_guide,
)
from audio_core.models import (
    Analysis,
    Grid,
    KeyInfo,
    SectionName,
    Sections,
    StagePackOptions,
    StemSet,
)
from audio_core.timeline import Timeline, TimelineError, build_timeline, section_cues

TICKS_PER_BEAT = 480
FALLBACK_TITLE = "Stage Pack"
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Stem name (from the StemSet) -> (playback name, daw name), in pack order.
STEM_NAMES: dict[str, tuple[str, str]] = {
    "drums": ("Drums", "Batería"),
    "bass": ("Bass", "Bajo"),
    "piano": ("Keys", "Teclados"),
    "guitar": ("Electric Guitar", "Guitarra eléctrica"),
    "other": ("Tracks", "Pistas"),
    "vocals": ("Vocals", "Voz"),
}
CLICK_NAMES = ("Click", "Click")
GUIDE_NAMES = ("Guide", "Guía")
SPLIT_NAMES = ("Split Track", "Split Track")

SECTION_LABELS: dict[str, dict[SectionName, str]] = {
    "es": {
        SectionName.INTRO: "Intro",
        SectionName.VERSE: "Estrofa",
        SectionName.VERSE_2: "Estrofa 2",
        SectionName.PRE_CHORUS: "Pre-coro",
        SectionName.CHORUS: "Coro",
        SectionName.BRIDGE: "Puente",
        SectionName.SOLO: "Solo",
        SectionName.INSTRUMENTAL: "Instrumental",
        SectionName.BREAK: "Break",
        SectionName.OUTRO: "Final",
        SectionName.TAG: "Tag",
    },
    "en": {
        SectionName.INTRO: "Intro",
        SectionName.VERSE: "Verse",
        SectionName.VERSE_2: "Verse 2",
        SectionName.PRE_CHORUS: "Pre-Chorus",
        SectionName.CHORUS: "Chorus",
        SectionName.BRIDGE: "Bridge",
        SectionName.SOLO: "Solo",
        SectionName.INSTRUMENTAL: "Instrumental",
        SectionName.BREAK: "Break",
        SectionName.OUTRO: "Outro",
        SectionName.TAG: "Tag",
    },
}

IMPORT_NOTES: dict[tuple[str, str], str] = {
    ("playback", "es"): """CÓMO IMPORTAR EN PLAYBACK

1. Sube este ZIP completo, sin descomprimirlo, como un solo archivo.
2. Designa el archivo "Guide" como pista de guía (Guide) para que salga solo por el retorno
   del músico y no por la mezcla de sala.
3. Usa 44.1 kHz o 48 kHz, 24 bits. Los archivos ya están a {rate} kHz, 24 bits.
4. Todos los archivos tienen exactamente la misma duración y empiezan en el mismo punto: la
   cuenta previa de {bars} compás(es) está incluida al inicio.
5. "Split Track" tiene el click y la guía a la izquierda y la banda a la derecha.
""",
    ("playback", "en"): """HOW TO IMPORT INTO PLAYBACK

1. Upload this whole ZIP, without unzipping it, as a single file.
2. Designate the "Guide" file as the Guide track so it plays only in the musician's monitor
   and not in the house mix.
3. Use 44.1 kHz or 48 kHz, 24-bit. The files are already {rate} kHz, 24-bit.
4. Every file has exactly the same length and starts at the same point: the {bars}-bar
   count-in is included at the start.
5. "Split Track" has the click and guide on the left and the band on the right.
""",
    ("daw", "es"): """CÓMO IMPORTAR EN TU DAW

1. Descomprime el ZIP.
2. Arrastra todos los WAV al proyecto y colócalos en el compás 1 (tiempo cero). Están
   alineados a la muestra: no muevas ni recortes ninguno.
3. Proyecto a {rate} kHz, 24 bits. La cuenta previa de {bars} compás(es) está incluida al inicio.
4. Importa "Tempo.mid" (mapa de tempo y marcadores de sección) si quieres que la cuadrícula
   del DAW siga la canción.
5. "Secciones.txt" lista cada sección con su compás y su tiempo.
6. "Split Track" tiene el click y la guía a la izquierda y la banda a la derecha.
""",
    ("daw", "en"): """HOW TO IMPORT INTO YOUR DAW

1. Unzip the package.
2. Drag all the WAV files into the project and place them at bar 1 (time zero). They are
   sample aligned: do not move or trim any of them.
3. Set the project to {rate} kHz, 24-bit. The {bars}-bar count-in is included at the start.
4. Import "Tempo.mid" (tempo map and section markers) if you want the DAW grid to follow the song.
5. "Secciones.txt" lists every section with its bar and time.
6. "Split Track" has the click and guide on the left and the band on the right.
""",
}
NO_SECTIONS = {
    "es": "No se proporcionaron secciones.",
    "en": "No sections were provided.",
}


class StagePackError(RuntimeError):
    """Raised when a Stage Pack cannot be built from the given inputs."""


@dataclass
class PackResult:
    zip_path: Path
    report: dict


def sanitize_filename(text: str) -> str:
    cleaned = _UNSAFE_FILENAME.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:120].strip(" .")


def key_label(key: KeyInfo | None) -> str | None:
    """ "G" for major, "Em" for minor; None when the key is unknown."""
    if key is None or key.mode not in ("major", "minor") or not key.key or key.key == "unknown":
        return None
    return key.key + ("m" if key.mode == "minor" else "")


def zip_name(title: str, key: KeyInfo | None, bpm: float) -> str:
    parts = [sanitize_filename(title) or FALLBACK_TITLE]
    label = key_label(key)
    if label:
        parts.append(sanitize_filename(label))
    parts.append(f"{round(bpm)} BPM")
    return " - ".join(parts) + ".zip"


def load_json_model(path: Path, model: type, what: str):  # noqa: ANN201
    try:
        return model.model_validate_json(Path(path).read_text("utf-8"))
    except OSError as exc:
        raise StagePackError(f"cannot read {what} {path}: {exc}") from exc
    except (ValidationError, ValueError) as exc:
        raise StagePackError(f"invalid {what} {path}: {exc}") from exc


def load_stems(stemset: StemSet, directory: Path) -> dict[str, np.ndarray]:
    """Load every stem as float32 (2, samples) at the internal rate, all the same length."""
    if stemset.sample_rate != SAMPLE_RATE:
        raise StagePackError(f"stems must be {SAMPLE_RATE} Hz, got {stemset.sample_rate}")
    stems: dict[str, np.ndarray] = {}
    for stem in stemset.stems:
        if stem.name not in STEM_NAMES:
            raise StagePackError(f"unsupported stem {stem.name!r}")
        path = directory / stem.path
        try:
            data, rate = sf.read(str(path), dtype="float32", always_2d=True)
        except (OSError, RuntimeError) as exc:
            raise StagePackError(f"cannot read stem {path}: {exc}") from exc
        if rate != SAMPLE_RATE:
            raise StagePackError(f"stem {path} is {rate} Hz, expected {SAMPLE_RATE}")
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] != 2:
            raise StagePackError(f"stem {path} has {data.shape[1]} channels, expected 1 or 2")
        stems[stem.name] = np.ascontiguousarray(data.T, dtype=DTYPE)
    if not stems:
        raise StagePackError("the stem set has no stems")
    lengths = {name: audio.shape[1] for name, audio in stems.items()}
    if len(set(lengths.values())) != 1:
        raise StagePackError(f"stems differ in length: {lengths}")
    return stems


def _export_length(total_samples: int, sample_rate: int) -> int:
    return round(total_samples * sample_rate / SAMPLE_RATE)


def _resample(audio: np.ndarray, sample_rate: int, frames: int) -> np.ndarray:
    """Resample (channels, n) from the internal rate and pad/trim to exactly ``frames``."""
    if sample_rate != SAMPLE_RATE:
        audio = soxr.resample(audio.T, SAMPLE_RATE, sample_rate).T
    audio = np.ascontiguousarray(audio, dtype=DTYPE)
    if audio.shape[1] > frames:
        return audio[:, :frames]
    if audio.shape[1] < frames:
        return np.pad(audio, ((0, 0), (0, frames - audio.shape[1])))
    return audio


def _safe_gain(signal: np.ndarray) -> float:
    """Gain (<= 1) that keeps ``signal`` within full scale; 1.0 when it already fits."""
    peak = float(np.max(np.abs(signal))) if signal.size else 0.0
    return 1.0 if peak <= 1.0 else 1.0 / peak


def split_track(
    click: np.ndarray, guide: np.ndarray, band: list[np.ndarray]
) -> tuple[np.ndarray, dict[str, float]]:
    """Stereo split: left = click + guide, right = mono sum of the band stems.

    Inputs are (channels, n) at the export rate. Each side is scaled down only if it would clip.
    """
    left = click.mean(axis=0) + guide.mean(axis=0)
    right = np.zeros_like(left)
    for stem in band:
        right += stem.mean(axis=0)
    gain_left, gain_right = _safe_gain(left), _safe_gain(right)
    out = np.stack([left * gain_left, right * gain_right]).astype(DTYPE)
    return out, {"left": gain_left, "right": gain_right}


def destination_names(
    present: list[str], destination: str, include_vocals: bool
) -> tuple[str, str, dict[str, str], str]:
    """File base names (no extension): click, guide, per-stem, split. Daw names are numbered."""
    index = 0 if destination == "playback" else 1
    stems = [s for s in STEM_NAMES if s in present and (s != "vocals" or include_vocals)]
    bases = [CLICK_NAMES[index], GUIDE_NAMES[index]]
    bases += [STEM_NAMES[s][index] for s in stems] + [SPLIT_NAMES[index]]
    if destination == "daw":
        bases = [f"{n:02d} {base}" for n, base in enumerate(bases, start=1)]
    return bases[0], bases[1], dict(zip(stems, bases[2:-1], strict=True)), bases[-1]


def _clock(samples: int) -> str:
    millis = round(samples * 1000 / SAMPLE_RATE)
    minutes, millis = divmod(millis, 60_000)
    return f"{minutes:02d}:{millis // 1000:02d}.{millis % 1000:03d}"


def bar_starts(timeline: Timeline) -> list[int]:
    """Pack-time bar boundaries: count-in bars, then every detected downbeat.

    With a long intro the count-in starts after sample 0; a leading virtual bar from sample 0 keeps
    bar 1 at time zero so the later bars stay aligned (the tempo map stretches that bar).
    """
    starts = [
        timeline.count_in_start + i * timeline.bar_samples for i in range(timeline.count_in_bars)
    ]
    starts += list(timeline.downbeats)
    if starts[0] > 0:
        starts.insert(0, 0)
    return starts


def secciones_text(timeline: Timeline, sections: Sections | None, language: str) -> str:
    starts = bar_starts(timeline)
    if sections is None or not sections.sections:
        return NO_SECTIONS[language] + "\n"
    labels = SECTION_LABELS[language]
    lines = []
    for placed in section_cues(timeline, sections.sections):
        label = placed.section.label or labels[placed.section.name]
        bar = starts.index(placed.downbeat) + 1
        lines.append(f"{label}\tbar {bar}\t{_clock(placed.downbeat)}")
    return "\n".join(lines) + "\n"


def tempo_map(timeline: Timeline, grid: Grid, sections: Sections | None) -> mido.MidiFile:
    """MIDI file with one tempo event per bar (pack time) and a marker per section."""
    denominator = grid.time_signature.partition("/")[2]
    den = int(denominator) if denominator.isdigit() and int(denominator) in (2, 4, 8, 16) else 4
    num = timeline.beats_per_bar
    quarters_per_bar = num * 4 / den
    bar_ticks = round(quarters_per_bar * TICKS_PER_BEAT)

    starts = bar_starts(timeline)
    lengths = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    lengths.append(lengths[-1] if lengths else timeline.bar_samples)

    events: list[tuple[int, int, mido.MetaMessage]] = [
        (0, 0, mido.MetaMessage("time_signature", numerator=num, denominator=den))
    ]
    for i, length in enumerate(lengths):
        micros = round(length / SAMPLE_RATE * 1_000_000 / quarters_per_bar)
        events.append((i * bar_ticks, 1, mido.MetaMessage("set_tempo", tempo=micros)))
    if sections is not None:
        labels = SECTION_LABELS["en"]
        for placed in section_cues(timeline, sections.sections):
            bar = starts.index(placed.downbeat)
            text = placed.section.label or labels[placed.section.name]
            events.append((bar * bar_ticks, 2, mido.MetaMessage("marker", text=text)))

    track = mido.MidiTrack([mido.MetaMessage("track_name", name="Tempo", time=0)])
    previous = 0
    for tick, _, message in sorted(events, key=lambda e: (e[0], e[1])):
        track.append(message.copy(time=tick - previous))
        previous = tick
    track.append(mido.MetaMessage("end_of_track", time=0))
    midi = mido.MidiFile(type=0, ticks_per_beat=TICKS_PER_BEAT)
    midi.tracks.append(track)
    return midi


def _load_library(cues_dir: Path | None, language: str, warnings: list[str]) -> CueLibrary | None:
    directory = Path(cues_dir) if cues_dir else default_library_dir(language)
    try:
        return CueLibrary(directory)
    except CueLibraryError as exc:
        warnings.append(f"cue library unavailable, the Guide is silent: {exc}")
        return None


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    sf.write(str(path), np.clip(audio, -1.0, 1.0).T, sample_rate, subtype="PCM_24")


def build_stagepack(
    stemset: StemSet,
    stems_dir: Path,
    analysis: Analysis,
    sections: Sections | None,
    options: StagePackOptions,
    out_dir: Path,
    cues_dir: Path | None = None,
) -> PackResult:
    """Build the Stage Pack ZIP in ``out_dir`` and return its path and report."""
    if analysis.grid is None or not analysis.grid.downbeats or len(analysis.grid.beats) < 2:
        raise StagePackError("analysis has no usable beat grid (beats and downbeats are required)")
    stems = load_stems(stemset, Path(stems_dir))
    original_samples = next(iter(stems.values())).shape[1]
    try:
        timeline = build_timeline(analysis.grid, options.count_in_bars, SAMPLE_RATE)
    except TimelineError as exc:
        raise StagePackError(f"cannot build the count-in timeline: {exc}") from exc

    total = timeline.total_samples(original_samples)
    frames = _export_length(total, options.sample_rate)
    pad = timeline.pad_samples
    warnings: list[str] = []

    click = render_click(timeline, total, options)
    library = _load_library(cues_dir, options.language, warnings)
    if library is None:
        guide = np.zeros(total, dtype=DTYPE)
    else:
        guide, guide_report = render_guide(timeline, total, sections, library)
        warnings += guide_report.warnings

    click_name, guide_name, stem_names, split_name = destination_names(
        list(stems), options.destination, options.include_vocals
    )
    rate = options.sample_rate

    def export(audio: np.ndarray) -> np.ndarray:
        return _resample(audio, rate, frames)

    click_out = export(click[None, :])
    guide_out = export(guide[None, :])
    band_out = {name: export(np.pad(stems[name], ((0, 0), (pad, 0)))) for name in stem_names}
    split_out, split_gain = split_track(click_out, guide_out, list(band_out.values()))

    tracks = [(click_name, click_out), (guide_name, guide_out)]
    tracks += [(stem_names[name], audio) for name, audio in band_out.items()]
    tracks.append((split_name, split_out))

    title = Path(stemset.source or analysis.source).stem
    archive_name = zip_name(title, analysis.key, analysis.grid.bpm)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / archive_name

    models = {name: m.model_dump() for name, m in analysis.models.items()}
    models["separation"] = stemset.model.model_dump()
    files = [f"{name}.wav" for name, _ in tracks]
    files += ["Secciones.txt", "Tempo.mid", "Cómo importar.txt", "stagepack.json"]
    report = {
        "options": options.model_dump(),
        "pad_samples": pad,
        "sample_rate": rate,
        "frame_count": frames,
        "files": files,
        "click_onsets": len(click_events(timeline, total, options)),
        "guide_warnings": warnings,
        "split_gain": split_gain,
        "models": models,
    }

    notes = IMPORT_NOTES[(options.destination, options.language)].format(
        rate=f"{rate / 1000:g}", bars=options.count_in_bars
    )
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(zip_path, "w") as archive:
        for name, audio in tracks:
            wav = Path(tmp) / f"{name}.wav"
            _write_wav(wav, audio, rate)
            archive.write(wav, f"{name}.wav", compress_type=zipfile.ZIP_DEFLATED)
            wav.unlink()
        archive.writestr(
            "Secciones.txt", secciones_text(timeline, sections, options.language).encode("utf-8")
        )
        midi_path = Path(tmp) / "Tempo.mid"
        tempo_map(timeline, analysis.grid, sections).save(str(midi_path))
        archive.write(midi_path, "Tempo.mid")
        archive.writestr("Cómo importar.txt", notes.encode("utf-8"))
        archive.writestr("stagepack.json", json.dumps(report, indent=2, ensure_ascii=False))
    return PackResult(zip_path=zip_path, report=report)
