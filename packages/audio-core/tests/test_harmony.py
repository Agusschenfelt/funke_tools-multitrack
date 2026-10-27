import importlib.util

import numpy as np
import pytest

from audio_core.harmony import (
    CHORD_OVERRIDE_MARGIN,
    ChordHint,
    KeyCandidate,
    chord_key_hint,
    chord_segments,
    decide_key,
    detect_chords,
    estimate_key_with_chords,
    parse_chord,
)
from audio_core.models import Analysis, Chord, KeyInfo

requires_essentia = pytest.mark.skipif(
    importlib.util.find_spec("essentia") is None, reason="essentia is not installed"
)

A, C_SHARP, D, E, F_SHARP = 9, 1, 2, 4, 6
BEATS = [i * 0.5 for i in range(33)]


def seq(*labels: str, beats_each: int = 4) -> list[Chord]:
    out = []
    for i, label in enumerate(labels):
        out.append(Chord(start=i * beats_each * 0.5, end=(i + 1) * beats_each * 0.5, label=label))
    return out


# --- chord segments ---


def test_repeats_merge_into_one_segment() -> None:
    segments = chord_segments(["A"] * 4 + ["E"] * 4, BEATS)
    assert [(c.label, c.start, c.end) for c in segments] == [("A", 0.0, 2.0), ("E", 2.0, 4.0)]


def test_flats_become_sharps_and_no_chord_is_dropped() -> None:
    segments = chord_segments(["Bb"] * 3 + ["N"] * 3 + ["Ebm"] * 3, BEATS)
    assert [c.label for c in segments] == ["A#", "D#m"]


def test_single_beat_flicker_is_absorbed() -> None:
    segments = chord_segments(["A", "A", "A", "D", "A", "A", "E", "E", "E", "E"], BEATS)
    assert [c.label for c in segments] == ["A", "E"]
    assert segments[0].end == segments[1].start == 3.0


def test_short_run_goes_to_the_longer_neighbour() -> None:
    segments = chord_segments(["A", "A", "A", "A", "D", "E", "E"], BEATS)
    assert [c.label for c in segments] == ["A", "E"]
    assert segments[0].end == 2.5


def test_min_beats_one_keeps_every_beat() -> None:
    segments = chord_segments(["A", "D", "E"], BEATS, min_beats=1)
    assert [c.label for c in segments] == ["A", "D", "E"]


def test_segments_never_overlap_and_stay_ordered() -> None:
    rng = np.random.default_rng(3)
    labels = [str(rng.choice(["A", "D", "E", "C#m", "N"])) for _ in range(32)]
    segments = chord_segments(labels, BEATS)
    for before, after in zip(segments, segments[1:], strict=False):
        assert before.end <= after.start
    assert all(c.end > c.start for c in segments)


def test_no_beats_or_labels_give_no_segments() -> None:
    assert chord_segments([], BEATS) == []
    assert chord_segments(["A"], [0.0]) == []


def test_parse_chord() -> None:
    assert parse_chord("C#m") == (1, "m")
    assert parse_chord("Bb") == (10, "M")
    assert parse_chord("N") is None
    assert parse_chord("H") is None


# --- tonic hint ---


def test_hint_prefers_the_tonic_over_its_dominant() -> None:
    # A D E A with ends on the tonic: A major, not E major (the dominant key shares A, D, E).
    hint = chord_key_hint(seq("A", "C#m", "D", "E", "A", "D", "E", "A"))
    assert (hint.pitch_class, hint.mode) == (A, "major")


def test_hint_breaks_relative_tie_with_cadence_and_final_chord() -> None:
    minor = chord_key_hint(seq("C#m", "A", "E", "B", "C#m", "A", "B", "C#m"))
    assert (minor.pitch_class, minor.mode) == (C_SHARP, "minor")
    major = chord_key_hint(seq("E", "A", "B", "E", "C#m", "A", "B", "E"))
    assert (major.pitch_class, major.mode) == (E, "major")


def test_hint_of_nothing_is_none() -> None:
    assert chord_key_hint([]) is None
    assert chord_key_hint([Chord(start=0, end=2, label="N")]) is None


def test_hint_reports_the_reference_key_score() -> None:
    chords = seq("A", "D", "E", "A")
    hint = chord_key_hint(chords, KeyCandidate(E, "major"))
    assert hint is not None
    assert hint.score > hint.runner_up_score


# --- key decision ---


def test_agreeing_chords_and_profiles_give_no_alternative() -> None:
    primary = KeyCandidate(A, "major", 0.85)
    panel = [KeyCandidate(A, "major", 0.8)] * 5 + [KeyCandidate(E, "major", 0.4)]
    chosen, alternative, _ = decide_key(primary, panel, ChordHint(A, "major", 1.3, 1.3))
    assert (chosen.pitch_class, alternative) == (A, None)


def test_clearly_better_chord_key_replaces_the_profile_key() -> None:
    primary = KeyCandidate(E, "major", 0.84)
    chosen, alternative, reason = decide_key(primary, [primary], ChordHint(A, "major", 1.32, 1.07))
    assert (chosen.pitch_class, chosen.mode) == (A, "major")
    assert (alternative.key, alternative.mode, alternative.camelot) == ("E", "major", "12B")
    assert "chords" in reason


def test_a_marginal_chord_disagreement_keeps_the_profile_key_as_primary() -> None:
    primary = KeyCandidate(E, "major", 0.84)
    score = 1.0
    hint = ChordHint(C_SHARP, "minor", score, score - CHORD_OVERRIDE_MARGIN / 2)
    chosen, alternative, _ = decide_key(primary, [primary], hint)
    assert chosen.pitch_class == E
    assert (alternative.key, alternative.mode) == ("C#", "minor")


def test_split_profiles_expose_the_runner_up_without_chords() -> None:
    primary = KeyCandidate(E, "major", 0.84)
    panel = [
        primary,
        KeyCandidate(E, "major", 0.8),
        KeyCandidate(A, "major", 0.83),
        KeyCandidate(A, "major", 0.8),
    ]
    chosen, alternative, reason = decide_key(primary, panel, None)
    assert chosen.pitch_class == E
    assert (alternative.key, alternative.mode) == ("A", "major")
    assert "split" in reason


def test_a_weak_runner_up_is_not_an_alternative() -> None:
    primary = KeyCandidate(E, "major", 0.9)
    panel = [primary] * 5 + [KeyCandidate(A, "major", 0.7)]
    assert decide_key(primary, panel, None)[1] is None


# --- models ---


def test_key_info_without_the_new_fields_still_validates() -> None:
    info = KeyInfo(key="E", mode="major", camelot="12B", compatible=[])
    assert info.alternative is None and info.confidence is None


def test_analysis_chords_and_alternative_round_trip() -> None:
    analysis = Analysis.model_validate(
        {
            "source": "x",
            "duration": 1,
            "sample_rate": 44100,
            "grid": None,
            "key": {
                "key": "A",
                "mode": "major",
                "camelot": "11B",
                "compatible": [],
                "confidence": 0.8,
                "alternative": {"key": "E", "mode": "major", "camelot": "12B"},
            },
            "loudness": None,
            "models": {},
            "chords": [{"start": 0, "end": 2, "label": "A"}],
        }
    )
    again = Analysis.model_validate_json(analysis.model_dump_json())
    assert again.key and again.key.alternative and again.key.alternative.key == "E"
    assert again.chords == [Chord(start=0, end=2, label="A")]


def test_analysis_without_chords_validates() -> None:
    analysis = Analysis(
        source="x", duration=1, sample_rate=44100, grid=None, key=None, loudness=None, models={}
    )
    assert analysis.chords is None


# --- Essentia (skipped when not installed) ---


def _triad(root_hz: float, minor: bool, seconds: float, sr: int = 44100) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    third = 6 / 5 if minor else 5 / 4
    return sum(
        np.sin(2 * np.pi * root_hz * ratio * h * t) / h
        for ratio in (1, third, 3 / 2)
        for h in (1, 2, 3)
    ).astype(np.float32)


@requires_essentia
def test_synthetic_progression_is_labelled_by_essentia() -> None:
    sr, beat = 44100, 0.5
    audio = np.concatenate(
        [
            _triad(220.0, False, 8 * beat),
            _triad(329.63, False, 8 * beat),
            _triad(220.0, False, 8 * beat),
        ]
    )
    beats = [i * beat for i in range(int(len(audio) / sr / beat) + 1)]
    chords = detect_chords(audio, beats)
    assert [c.label for c in chords][:2] == ["A", "E"]


@requires_essentia
def test_essentia_key_of_a_synthetic_chord_loop() -> None:
    audio = np.concatenate(
        [
            _triad(220.0, False, 2.0),
            _triad(293.66, False, 2.0),
            _triad(329.63, False, 2.0),
            _triad(220.0, False, 2.0),
        ]
        * 3
    )
    chords = chord_segments(["A"] * 4 + ["D"] * 4 + ["E"] * 4 + ["A"] * 4, BEATS)
    chosen, info, _ = estimate_key_with_chords(audio, chords)
    assert chosen is not None and info is not None
    assert info.key == "A" and info.mode == "major"
    assert info.confidence is not None


def test_nan_key_strength_is_no_evidence_not_certainty(monkeypatch: pytest.MonkeyPatch) -> None:
    from audio_core import harmony

    class FakeExtractor:
        def __init__(self, **_kwargs) -> None:
            pass

        def __call__(self, _mono):
            return "A", "minor", float("nan")

    class FakeEs:
        KeyExtractor = FakeExtractor

    monkeypatch.setattr(harmony, "_essentia", lambda: FakeEs)
    candidate = harmony._key_candidate(np.zeros(10, dtype=np.float32), "bgate")
    assert candidate is not None and candidate.strength == 0.0
    _chosen, info, _reason = estimate_key_with_chords(np.zeros(10, dtype=np.float32), None)
    assert info is not None and info.confidence == 0.0
