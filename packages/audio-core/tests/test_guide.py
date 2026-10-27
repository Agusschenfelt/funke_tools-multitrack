import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from audio_core.constants import SAMPLE_RATE
from audio_core.guide import (
    CUE_IDS,
    ONSET_THRESHOLD,
    CueLibrary,
    CueLibraryError,
    count_cue_ids,
    load_cue_audio,
    render_guide,
)
from audio_core.models import Grid, Section, SectionName, Sections
from audio_core.timeline import build_timeline, section_cues

SR = SAMPLE_RATE
LEAD_SILENCE = 0.005  # seconds of silence before the tone in every synthetic cue
TONE_SECONDS = 0.25
TONE_AMPLITUDE = 0.8


def make_grid(bpm: float, bpb: int, t0: float, bars: int = 8, signature: str | None = None) -> Grid:
    interval = 60.0 / bpm
    beats = [t0 + i * interval for i in range(bars * bpb)]
    return Grid(
        bpm=bpm, beats=beats, downbeats=beats[::bpb], time_signature=signature or f"{bpb}/4"
    )


def write_cue(path: Path, freq: float, rate: int = SR, seconds: float = TONE_SECONDS) -> None:
    """Silence, then a Hann-windowed tone whose first loud sample is well above the threshold."""
    lead = np.zeros(int(LEAD_SILENCE * rate))
    n = int(seconds * rate)
    tone = TONE_AMPLITUDE * np.sin(2 * np.pi * freq * np.arange(n) / rate) * np.hanning(n + 2)[1:-1]
    # A flat start keeps the onset sample unambiguous: ramp over 1 ms instead of from zero.
    ramp = min(int(0.001 * rate), n)
    tone[:ramp] = TONE_AMPLITUDE * np.sin(2 * np.pi * freq * np.arange(ramp) / rate + 1.0)
    sf.write(str(path), np.concatenate([lead, tone]).astype(np.float32), rate)


def build_library(
    directory: Path, skip: tuple[str, ...] = (), no_file: tuple[str, ...] = ()
) -> Path:
    """One tone per cue id (different pitch each); ``count_1`` is stored at 48 kHz."""
    directory.mkdir(parents=True, exist_ok=True)
    cues = {}
    for i, cue_id in enumerate(CUE_IDS):
        if cue_id in skip:
            continue
        name = f"{cue_id}.wav"
        if cue_id not in no_file:
            write_cue(directory / name, 300 + 40 * i, rate=48000 if cue_id == "count_1" else SR)
        cues[cue_id] = {"file": name, "license": "CC0", "source": "synthetic test tone"}
    manifest = {"language": "es", "voice": {"name": "test"}, "cues": cues}
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


@pytest.fixture
def library(tmp_path: Path) -> CueLibrary:
    return CueLibrary(build_library(tmp_path / "es"))


def dominant_freq(segment: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment))))
    return float(np.argmax(spectrum) * SR / len(segment))


def test_onset_is_trimmed_to_the_first_loud_sample(tmp_path: Path) -> None:
    write_cue(tmp_path / "a.wav", 440)
    audio = load_cue_audio(tmp_path / "a.wav")
    assert abs(audio[0]) >= ONSET_THRESHOLD
    assert len(audio) == round(TONE_SECONDS * SR)


def test_resamples_to_internal_rate_and_mono(tmp_path: Path) -> None:
    n = int(0.2 * 48000)
    stereo = np.stack([np.sin(2 * np.pi * 500 * np.arange(n) / 48000)] * 2, axis=1) * 0.5
    sf.write(str(tmp_path / "s.wav"), stereo.astype(np.float32), 48000)
    audio = load_cue_audio(tmp_path / "s.wav")
    assert audio.dtype == np.float32 and audio.ndim == 1
    assert abs(len(audio) - 0.2 * SR) <= 2
    assert dominant_freq(audio[:4096]) == pytest.approx(500, abs=15)


def test_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(CueLibraryError):
        CueLibrary(tmp_path)


def test_invalid_manifest_raises(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text('{"language": "es"}', encoding="utf-8")
    with pytest.raises(CueLibraryError):
        CueLibrary(tmp_path)


@pytest.mark.parametrize(
    ("bpb", "expected"),
    [
        (4, ["count_1", "count_2", "count_3", "count_4"]),
        (3, ["count_1", "count_2", "count_3"]),
        (6, ["count_1", None, None, "count_2", None, None]),
        (
            12,
            ["count_1", None, None, "count_2", None, None, "count_3", None, None, "count_4"]
            + [None, None],
        ),
        (5, ["count_1", "count_2", "count_3", "count_4", None]),
    ],
)
def test_count_patterns(bpb: int, expected: list[str | None]) -> None:
    assert count_cue_ids(bpb) == expected


def test_section_cue_onset_error_is_zero_samples(library: CueLibrary) -> None:
    # Brief test 3: each section cue starts exactly at timeline.section_cues(...).cue.
    timeline = build_timeline(make_grid(120, 4, 0.5, bars=12))
    sections = Sections(
        sections=[
            Section(name=SectionName.VERSE, start=4.5),
            Section(name=SectionName.CHORUS, start=8.5),
            Section(name=SectionName.OUTRO, start=14.5),
        ]
    )
    total = timeline.total_samples(14 * SR)
    guide, report = render_guide(timeline, total, sections, library)
    expected = {c.section.name.value: c.cue for c in section_cues(timeline, sections.sections)}
    placed = {p.cue_id: p.sample for p in report.placed}
    for cue_id, sample in expected.items():
        assert placed[cue_id] == sample
        assert abs(guide[sample]) >= ONSET_THRESHOLD
        assert guide[sample - 1] == 0.0
    assert report.warnings == []


@pytest.mark.parametrize(
    ("bpm", "bpb", "signature", "expected_ids"),
    [
        (120, 4, "4/4", ["count_1", "count_2", "count_3", "count_4"]),
        (90, 3, "3/4", ["count_1", "count_2", "count_3"]),
        (180, 6, "6/8", ["count_1", "count_2"]),
    ],
)
def test_counting_sits_on_count_in_beats(
    library: CueLibrary, bpm: float, bpb: int, signature: str, expected_ids: list[str]
) -> None:
    timeline = build_timeline(make_grid(bpm, bpb, 0.5, signature=signature), count_in_bars=1)
    guide, report = render_guide(timeline, timeline.total_samples(10 * SR), None, library)
    assert [p.cue_id for p in report.placed] == expected_ids
    pulse = 3 if bpb == 6 else 1
    beats = timeline.count_in_beats[::pulse][: len(expected_ids)]
    assert [p.sample for p in report.placed] == list(beats)
    # Nothing is spoken outside the count-in when there are no sections.
    assert not guide[timeline.first_downbeat :].any()


def test_two_bar_count_in_counts_twice(library: CueLibrary) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5), count_in_bars=2)
    _, report = render_guide(timeline, timeline.total_samples(10 * SR), None, library)
    assert [p.cue_id for p in report.placed] == ["count_1", "count_2", "count_3", "count_4"] * 2


def test_no_sections_only_counts(library: CueLibrary) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))
    _, report = render_guide(timeline, timeline.total_samples(10 * SR), None, library)
    assert {p.cue_id for p in report.placed} == set(CUE_IDS[-4:])


def test_each_cue_plays_its_own_sample(library: CueLibrary) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5, bars=12))
    sections = Sections(sections=[Section(name=SectionName.BRIDGE, start=8.5)])
    guide, report = render_guide(timeline, timeline.total_samples(14 * SR), sections, library)
    for placed in report.placed:
        freq = 300 + 40 * CUE_IDS.index(placed.cue_id)
        segment = guide[placed.sample : placed.sample + 4096]
        assert dominant_freq(segment) == pytest.approx(freq, abs=15)


def test_missing_sample_and_manifest_entry_warn_without_crashing(tmp_path: Path) -> None:
    library = CueLibrary(build_library(tmp_path / "es", skip=("chorus",), no_file=("verse",)))
    timeline = build_timeline(make_grid(120, 4, 0.5, bars=12))
    sections = Sections(
        sections=[
            Section(name=SectionName.VERSE, start=4.5),
            Section(name=SectionName.CHORUS, start=8.5),
            Section(name=SectionName.BRIDGE, start=12.5),
        ]
    )
    _, report = render_guide(timeline, timeline.total_samples(14 * SR), sections, library)
    assert {p.cue_id for p in report.placed} >= {"bridge", "count_1"}
    assert not {"verse", "chorus"} & {p.cue_id for p in report.placed}
    assert any("verse" in w for w in report.warnings)
    assert any("chorus" in w and "manifest" in w for w in report.warnings)


def test_length_is_exact_and_peak_is_within_range(library: CueLibrary) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5, bars=12))
    sections = Sections(sections=[Section(name=SectionName.SOLO, start=6.5)])
    total = timeline.total_samples(14 * SR)
    guide, _ = render_guide(timeline, total, sections, library)
    assert guide.shape == (total,)
    assert guide.dtype == np.float32
    assert np.abs(guide).max() <= 1.0


def test_overlap_truncates_earlier_cue_and_never_sums(tmp_path: Path) -> None:
    # 300 BPM: a beat is 0.2 s, shorter than the 0.25 s cue, so each count is cut by the next.
    library = CueLibrary(build_library(tmp_path / "es"))
    timeline = build_timeline(make_grid(300, 4, 0.5))
    guide, report = render_guide(timeline, timeline.total_samples(6 * SR), None, library)
    beat = round(60 / 300 * SR)
    first = report.placed[0]
    assert first.length == beat < round(TONE_SECONDS * SR)
    # Summing two cues would reach ~1.6; resampling overshoot stays far below that.
    assert np.abs(guide).max() < 0.9
    # The fade brings the cut cue to silence just before the next onset.
    assert abs(guide[first.sample + beat - 1]) < 0.01


def test_section_cue_on_a_count_beat_is_dropped_with_warning(library: CueLibrary) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))
    sections = Sections(sections=[Section(name=SectionName.INTRO, start=0.5)])
    _, report = render_guide(timeline, timeline.total_samples(10 * SR), sections, library)
    assert "intro" not in {p.cue_id for p in report.placed}
    assert report.placed[0].cue_id == "count_1"
    assert any("intro" in w for w in report.warnings)


def test_cue_truncated_at_the_end_not_wrapped(library: CueLibrary) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))
    total = timeline.count_in_beats[-1] + 1000
    guide, report = render_guide(timeline, total, None, library)
    last = report.placed[-1]
    assert last.length == 1000
    assert guide.shape == (total,)
    assert not guide[: timeline.count_in_beats[0]].any()
    assert guide[total - 1] != 0.0


def test_cue_after_the_end_is_skipped(library: CueLibrary) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))
    guide, report = render_guide(timeline, timeline.count_in_beats[1], None, library)
    assert [p.cue_id for p in report.placed] == ["count_1"]
    assert any("count_2" in w for w in report.warnings)
    assert guide.shape == (timeline.count_in_beats[1],)


def test_guide_is_its_own_buffer(library: CueLibrary) -> None:
    timeline = build_timeline(make_grid(120, 4, 0.5))
    total = timeline.total_samples(10 * SR)
    band = np.full((2, total), 0.1, dtype=np.float32)
    before = band.copy()
    guide, _ = render_guide(timeline, total, None, library)
    assert not np.shares_memory(guide, band)
    np.testing.assert_array_equal(band, before)


def test_malformed_manifest_json_raises_cue_library_error(tmp_path: Path) -> None:
    directory = tmp_path / "bad"
    directory.mkdir()
    (directory / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CueLibraryError):
        CueLibrary(directory)
    (directory / "manifest.json").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(CueLibraryError):
        CueLibrary(directory)


def test_guide_uses_the_timeline_rate_and_rejects_a_mismatched_library(tmp_path: Path) -> None:
    directory = build_library(tmp_path / "es")
    timeline = build_timeline(make_grid(120, 4, 0.5), sample_rate=48000)
    total = timeline.total_samples(5 * 48000)
    with pytest.raises(CueLibraryError, match="rate"):
        render_guide(timeline, total, None, CueLibrary(directory))
    library = CueLibrary(directory, sample_rate=48000)
    guide, report = render_guide(timeline, total, None, library)
    assert guide.shape == (total,)
    # A 0.25 s cue at 48 kHz is 12000 samples; at the wrong rate it would be 11025.
    assert report.placed[0].length == round(TONE_SECONDS * 48000)
