import io
import json
import zipfile
from pathlib import Path

import mido
import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

from audio_core.cli import app
from audio_core.constants import SAMPLE_RATE
from audio_core.models import (
    Analysis,
    Grid,
    KeyInfo,
    ModelVersion,
    Section,
    SectionName,
    Sections,
    StagePackOptions,
    Stem,
    StemSet,
)
from audio_core.stagepack import (
    StagePackError,
    build_stagepack,
    destination_names,
    sanitize_filename,
    split_track,
    zip_name,
)
from tests.test_guide import build_library

runner = CliRunner()

SECONDS = 8
STEM_FREQS = {
    "drums": 200,
    "bass": 110,
    "piano": 330,
    "guitar": 440,
    "other": 550,
    "vocals": 660,
}
SIX = ("drums", "bass", "piano", "guitar", "other", "vocals")
FOUR = ("drums", "bass", "other", "vocals")


class Inputs:
    def __init__(self, root: Path, names: tuple[str, ...], amplitude: float) -> None:
        self.stems_dir = root / "stems"
        self.stems_dir.mkdir()
        self.cues = build_library(root / "cues" / "es")
        self.out = root / "out"
        n = SECONDS * SAMPLE_RATE
        t = np.arange(n) / SAMPLE_RATE
        stems = []
        for name in names:
            mono = amplitude * np.sin(2 * np.pi * STEM_FREQS[name] * t)
            sf.write(str(self.stems_dir / f"{name}.wav"), np.stack([mono, mono], 1), SAMPLE_RATE)
            stems.append(Stem(name=name, path=f"{name}.wav", samples=n))
        self.stemset = StemSet(
            source="/music/Mi Canción.mp3",
            model=ModelVersion(name="htdemucs_6s", version="4.0"),
            device="cpu",
            elapsed_seconds=1,
            load_seconds=1,
            audio_seconds=SECONDS,
            samples=n,
            stems=stems,
        )
        beats = [1.0 + i * 0.5 for i in range(14)]
        self.analysis = Analysis(
            source="/music/Mi Canción.mp3",
            duration=SECONDS,
            sample_rate=SAMPLE_RATE,
            grid=Grid(bpm=120, beats=beats, downbeats=beats[::4], time_signature="4/4"),
            key=KeyInfo(key="G", mode="major", camelot="9B", compatible=[]),
            loudness=None,
            models={"beat": ModelVersion(name="beat_this", version="1")},
        )
        self.sections = Sections(
            sections=[
                Section(name=SectionName.VERSE, start=3.0),
                Section(name=SectionName.CHORUS, start=7.0),
            ]
        )
        (self.stems_dir / "stemset.json").write_text(self.stemset.model_dump_json(), "utf-8")
        (root / "analysis.json").write_text(self.analysis.model_dump_json(), "utf-8")
        (root / "sections.json").write_text(self.sections.model_dump_json(), "utf-8")
        self.root = root

    def build(self, sections: bool = True, **kwargs: object):
        kwargs.setdefault("destination", "daw")
        options = StagePackOptions(**kwargs)  # type: ignore[arg-type]
        return build_stagepack(
            self.stemset,
            self.stems_dir,
            self.analysis,
            self.sections if sections else None,
            options,
            self.out,
            cues_dir=self.cues,
        )


@pytest.fixture
def inputs(tmp_path: Path) -> Inputs:
    return Inputs(tmp_path, SIX, 0.2)


def read_wav(archive: zipfile.ZipFile, name: str) -> tuple[np.ndarray, int, str]:
    with sf.SoundFile(io.BytesIO(archive.read(name))) as f:
        return f.read(dtype="float32", always_2d=True).T, f.samplerate, f.subtype


def wav_names(archive: zipfile.ZipFile) -> list[str]:
    return [n for n in archive.namelist() if n.endswith(".wav")]


@pytest.mark.parametrize("rate", [44100, 48000])
def test_every_wav_has_the_same_frame_count(inputs: Inputs, rate: int) -> None:
    result = inputs.build(sample_rate=rate)
    expected = round((SECONDS * SAMPLE_RATE + SAMPLE_RATE) * rate / SAMPLE_RATE)
    with zipfile.ZipFile(result.zip_path) as archive:
        names = wav_names(archive)
        assert len(names) == 8  # click, guide, five band stems, split (no vocals)
        for name in names:
            audio, sr, subtype = read_wav(archive, name)
            assert audio.shape[1] == expected, name
            assert sr == rate and subtype == "PCM_24"
    assert result.report["frame_count"] == expected


def test_pack_starts_at_sample_zero_with_the_count_in(inputs: Inputs) -> None:
    result = inputs.build(destination="playback")
    with zipfile.ZipFile(result.zip_path) as archive:
        click, _, _ = read_wav(archive, "Click.wav")
        guide, _, _ = read_wav(archive, "Guide.wav")
        drums, _, _ = read_wav(archive, "Drums.wav")
    assert result.report["pad_samples"] == SAMPLE_RATE
    assert abs(click[0, 0]) > 0.5  # accented count-in click starts on sample 0
    assert abs(guide[0, 0]) > 0.01  # count_1 cue also starts on sample 0
    assert not drums[:, :SAMPLE_RATE].any()  # the song starts after the pad
    assert drums[:, SAMPLE_RATE + 1000 :].any()


def test_split_channels_follow_click_guide_and_band(inputs: Inputs) -> None:
    result = inputs.build(destination="playback")
    with zipfile.ZipFile(result.zip_path) as archive:
        click, _, _ = read_wav(archive, "Click.wav")
        guide, _, _ = read_wav(archive, "Guide.wav")
        split, _, _ = read_wav(archive, "Split Track.wav")
        band = sum(
            read_wav(archive, f"{n}.wav")[0][0]
            for n in ("Drums", "Bass", "Keys", "Electric Guitar", "Tracks")
        )
    assert split.shape[0] == 2
    gain = result.report["split_gain"]
    # The first beat sums click and guide above full scale, so the left side is scaled down.
    assert gain["left"] < 1.0 and gain["right"] == 1.0
    np.testing.assert_allclose(split[0], (click[0] + guide[0]) * gain["left"], atol=1e-4)
    np.testing.assert_allclose(split[1], band, atol=1e-4)


def test_vocals_are_excluded_unless_requested(tmp_path: Path) -> None:
    pack = Inputs(tmp_path, SIX, 0.1)
    default = pack.build(destination="playback")
    with zipfile.ZipFile(default.zip_path) as archive:
        assert "Vocals.wav" not in archive.namelist()
        right_default = read_wav(archive, "Split Track.wav")[0][1]
    with_vocals = pack.build(destination="playback", include_vocals=True)
    with zipfile.ZipFile(with_vocals.zip_path) as archive:
        vocals = read_wav(archive, "Vocals.wav")[0][0]
        right_with = read_wav(archive, "Split Track.wav")[0][1]
    np.testing.assert_allclose(right_with - right_default, vocals, atol=1e-4)


def test_split_track_normalizes_down_only_when_it_would_clip() -> None:
    quiet = np.full((1, 100), 0.3, dtype=np.float32)
    loud = np.full((1, 100), 0.9, dtype=np.float32)
    out, gain = split_track(quiet, quiet, [loud, loud])
    assert gain["left"] == 1.0
    assert gain["right"] == pytest.approx(1 / 1.8)
    assert np.max(np.abs(out)) <= 1.0
    np.testing.assert_allclose(out[0], 0.6, atol=1e-6)


def test_loud_stems_report_a_split_gain_below_one(tmp_path: Path) -> None:
    pack = Inputs(tmp_path, SIX, 0.9)
    result = pack.build()
    assert result.report["split_gain"]["right"] < 1.0
    with zipfile.ZipFile(result.zip_path) as archive:
        split = read_wav(archive, "08 Split Track.wav")[0]
    assert np.max(np.abs(split)) <= 1.0


def test_playback_names() -> None:
    click, guide, stems, split = destination_names(list(SIX), "playback", include_vocals=False)
    assert (click, guide, split) == ("Click", "Guide", "Split Track")
    assert stems == {
        "drums": "Drums",
        "bass": "Bass",
        "piano": "Keys",
        "guitar": "Electric Guitar",
        "other": "Tracks",
    }


def test_daw_names_are_numbered_contiguously() -> None:
    names = destination_names(list(SIX), "daw", include_vocals=True)
    flat = [names[0], names[1], *names[2].values(), names[3]]
    assert flat == [
        "01 Click",
        "02 Guía",
        "03 Batería",
        "04 Bajo",
        "05 Teclados",
        "06 Guitarra eléctrica",
        "07 Pistas",
        "08 Voz",
        "09 Split Track",
    ]


def test_four_stem_set_has_no_keys_or_guitar(tmp_path: Path) -> None:
    pack = Inputs(tmp_path, FOUR, 0.2)
    result = pack.build()
    with zipfile.ZipFile(result.zip_path) as archive:
        assert wav_names(archive) == [
            "01 Click.wav",
            "02 Guía.wav",
            "03 Batería.wav",
            "04 Bajo.wav",
            "05 Pistas.wav",
            "06 Split Track.wav",
        ]


def test_secciones_and_tempo_map(inputs: Inputs) -> None:
    result = inputs.build()
    with zipfile.ZipFile(result.zip_path) as archive:
        text = archive.read("Secciones.txt").decode("utf-8")
        midi = mido.MidiFile(file=io.BytesIO(archive.read("Tempo.mid")))
    assert text.splitlines() == ["Estrofa\tbar 3\t00:04.000", "Coro\tbar 5\t00:08.000"]
    messages = [m for m in midi.tracks[0] if m.is_meta]
    tempos = [m for m in messages if m.type == "set_tempo"]
    assert len(tempos) == 5  # count-in bar plus four detected bars
    assert all(m.tempo == 500000 for m in tempos)
    markers = []
    tick = 0
    for message in midi.tracks[0]:
        tick += message.time
        if message.type == "marker":
            markers.append((message.text, tick))
    assert markers == [("Verse", 2 * 1920), ("Chorus", 4 * 1920)]


def test_no_sections_note_and_no_markers(inputs: Inputs) -> None:
    result = inputs.build(sections=False, language="en")
    with zipfile.ZipFile(result.zip_path) as archive:
        assert archive.read("Secciones.txt").decode("utf-8").strip() == "No sections were provided."
        midi = mido.MidiFile(file=io.BytesIO(archive.read("Tempo.mid")))
    assert not [m for m in midi.tracks[0] if m.type == "marker"]


def test_import_notes_and_report_per_destination(inputs: Inputs) -> None:
    playback = inputs.build(destination="playback", language="en")
    with zipfile.ZipFile(playback.zip_path) as archive:
        notes = archive.read("Cómo importar.txt").decode("utf-8")
        report = json.loads(archive.read("stagepack.json"))
    assert "Guide" in notes and "single file" in notes
    assert report["pad_samples"] == SAMPLE_RATE and report["click_onsets"] > 0
    assert report["models"]["separation"]["name"] == "htdemucs_6s"
    daw = inputs.build(destination="daw")
    with zipfile.ZipFile(daw.zip_path) as archive:
        assert "compás 1" in archive.read("Cómo importar.txt").decode("utf-8")


def test_zip_name_and_sanitization() -> None:
    minor = KeyInfo(key="E", mode="minor", camelot="9A", compatible=[])
    assert zip_name("Song", minor, 119.6) == "Song - Em - 120 BPM.zip"
    assert zip_name('A/B: "C"?', None, 90) == "A B C - 90 BPM.zip"
    assert zip_name("../..", None, 90) == "Stage Pack - 90 BPM.zip"
    unknown = KeyInfo(key="unknown", mode="unknown", camelot="", compatible=[])
    assert zip_name("Song", unknown, 90) == "Song - 90 BPM.zip"
    assert sanitize_filename("  a\tb  ") == "a b"


def test_zip_file_name_comes_from_the_source_stem(inputs: Inputs) -> None:
    assert inputs.build().zip_path.name == "Mi Canción - G - 120 BPM.zip"


def test_missing_cue_library_builds_a_silent_guide(inputs: Inputs, tmp_path: Path) -> None:
    inputs.cues = tmp_path / "nowhere"
    result = inputs.build()
    assert result.report["guide_warnings"]
    with zipfile.ZipFile(result.zip_path) as archive:
        assert not read_wav(archive, "02 Guía.wav")[0].any()


def test_analysis_without_a_grid_is_rejected(inputs: Inputs) -> None:
    inputs.analysis = inputs.analysis.model_copy(update={"grid": None})
    with pytest.raises(StagePackError, match="beat grid"):
        inputs.build()


def run_cli(pack: Inputs, *extra: str):
    return runner.invoke(
        app,
        [
            "stagepack",
            str(pack.stems_dir),
            "--analysis",
            str(pack.root / "analysis.json"),
            "--out",
            str(pack.out),
            "--cues-dir",
            str(pack.cues),
            *extra,
        ],
    )


def test_cli_end_to_end(inputs: Inputs) -> None:
    result = run_cli(
        inputs,
        "--sections",
        str(inputs.root / "sections.json"),
        "--destination",
        "daw",
        "--sample-rate",
        "48000",
        "--count-in",
        "2",
        "--subdivision",
        "eighth",
        "--click-sound",
        "cowbell",
    )
    assert result.exit_code == 0, result.output
    zips = list(inputs.out.glob("*.zip"))
    assert [z.name for z in zips] == ["Mi Canción - G - 120 BPM.zip"]
    with zipfile.ZipFile(zips[0]) as archive:
        frames = {read_wav(archive, n)[0].shape[1] for n in wav_names(archive)}
        assert len(frames) == 1
        assert read_wav(archive, "01 Click.wav")[1] == 48000


@pytest.mark.parametrize(
    "extra",
    [["--destination", "prime"], ["--count-in", "3"], ["--sample-rate", "96000"]],
)
def test_cli_invalid_options_exit_1(inputs: Inputs, extra: list[str]) -> None:
    result = run_cli(inputs, *extra)
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert not inputs.out.exists()


def test_cli_missing_and_invalid_inputs_exit_1(inputs: Inputs) -> None:
    (inputs.root / "analysis.json").write_text("{not json", "utf-8")
    result = run_cli(inputs)
    assert result.exit_code == 1 and "analysis" in result.output
    (inputs.root / "analysis.json").unlink()
    assert run_cli(inputs).exit_code == 1
    result = runner.invoke(
        app, ["stagepack", str(inputs.root / "missing"), "--analysis", "x", "--out", "o"]
    )
    assert result.exit_code == 1 and "stemset.json" in result.output
