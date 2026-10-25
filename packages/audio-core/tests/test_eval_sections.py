import importlib.util
import json
import sys
from pathlib import Path

import pytest

from audio_core.io import write_wav
from audio_core.models import Analysis, Section, SectionName, Sections
from tests.conftest import requires_ffmpeg
from tests.test_sections import BAR_SECONDS, N_BARS, TRUE_BOUNDARY_BARS, make_song

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "eval_sections.py"
spec = importlib.util.spec_from_file_location("eval_sections", SCRIPT)
assert spec is not None and spec.loader is not None
ev = importlib.util.module_from_spec(spec)
sys.modules["eval_sections"] = ev
spec.loader.exec_module(ev)


def sections(*items: tuple[str, float]) -> Sections:
    return Sections(sections=[Section(name=SectionName(n), start=s) for n, s in items])


REFERENCE = sections(("intro", 0), ("verse", 10), ("chorus", 30), ("verse_2", 50), ("outro", 70))
EDGES = [float(t) for t in range(0, 81, 10)]


def test_perfect_match_scores_one() -> None:
    metrics = ev.song_metrics(REFERENCE, REFERENCE, EDGES)
    assert all(value == 1.0 for value in metrics.values())
    assert set(metrics) == set(ev.METRIC_KEYS)


def test_song_start_is_not_a_boundary() -> None:
    late_start = sections(("intro", 2), ("verse", 10), ("chorus", 30), ("verse_2", 50))
    assert ev.boundary_times(late_start) == [10, 30, 50]


def test_shift_within_and_outside_tolerance() -> None:
    reference = [10.0, 30.0, 50.0]
    within_both = [10.3, 30.2, 50.1]
    assert ev.hit_rate(reference, within_both, 0.5)["f"] == 1.0
    shifted = [11.0, 31.0, 51.0]
    assert ev.hit_rate(reference, shifted, 0.5)["f"] == 0.0
    assert ev.hit_rate(reference, shifted, 3.0)["f"] == 1.0


def test_precision_and_recall_differ_with_extra_and_missing_boundaries() -> None:
    result = ev.hit_rate([10.0, 30.0], [10.0, 20.0, 30.0, 40.0], 0.5)
    assert result["precision"] == 0.5
    assert result["recall"] == 1.0
    assert result["f"] == pytest.approx(2 / 3)


def test_matching_is_one_to_one() -> None:
    result = ev.hit_rate([10.0], [9.8, 10.2], 0.5)
    assert result["precision"] == 0.5
    assert result["recall"] == 1.0


def test_label_accuracy_strict_and_relaxed() -> None:
    estimate = sections(("intro", 0), ("verse", 10), ("chorus", 30), ("verse", 50), ("outro", 70))
    assert ev.label_accuracy(REFERENCE, estimate, EDGES) == 6 / 8
    assert ev.label_accuracy(REFERENCE, estimate, EDGES, relaxed=True) == 1.0


def test_label_accuracy_counts_bars_before_first_section_as_unlabeled() -> None:
    late = sections(("verse", 10), ("chorus", 30))
    assert ev.label_at(late, 5.0) is None
    assert ev.label_accuracy(late, late, EDGES) == 1.0


def test_empty_annotations() -> None:
    empty = Sections(sections=[])
    assert ev.hit_rate([], [], 3.0) == {"precision": 1.0, "recall": 1.0, "f": 1.0}
    assert ev.hit_rate([10.0], [], 3.0)["f"] == 0.0
    assert ev.hit_rate([], [10.0], 3.0)["f"] == 0.0
    assert ev.label_accuracy(empty, empty, EDGES) == 1.0
    assert ev.label_accuracy(REFERENCE, empty, EDGES) == 0.0
    assert ev.label_accuracy(REFERENCE, REFERENCE, [0.0]) == 0.0


def test_macro_average() -> None:
    zero = dict.fromkeys(ev.METRIC_KEYS, 0.0)
    one = dict.fromkeys(ev.METRIC_KEYS, 1.0)
    assert ev.macro_average([zero, one]) == dict.fromkeys(ev.METRIC_KEYS, 0.5)
    assert ev.macro_average([]) == {}


@requires_ffmpeg
def test_cli_main_writes_report_with_perfect_boundaries(tmp_path: Path) -> None:
    audio, _, grid = make_song()
    songs = tmp_path / "songs"
    songs.mkdir()
    write_wav(songs / "synthetic.wav", audio[None, :].repeat(2, axis=0))
    analysis = Analysis(
        source="synthetic.wav",
        duration=N_BARS * BAR_SECONDS,
        sample_rate=44100,
        grid=grid,
        key=None,
        loudness=None,
        models={},
    )
    (songs / "synthetic.analysis.json").write_text(analysis.model_dump_json(), encoding="utf-8")
    starts = [bar * BAR_SECONDS for bar in TRUE_BOUNDARY_BARS]
    truth = sections(
        *zip(
            ["intro", "verse", "chorus", "verse_2", "chorus", "bridge", "chorus", "outro"],
            starts,
            strict=True,
        )
    )
    (songs / "synthetic.sections.json").write_text(truth.model_dump_json(), encoding="utf-8")

    out = tmp_path / "out"
    assert ev.main([str(songs), "--out", str(out)]) == 0

    report = json.loads((out / "eval_report.json").read_text(encoding="utf-8"))
    assert [song["name"] for song in report["songs"]] == ["synthetic"]
    assert report["sections_model"]["version"]
    assert report["songs"][0]["metrics"]["hr_3_f"] == 1.0
    assert report["macro_average"]["hr_3_f"] == 1.0


def test_main_rejects_directory_without_annotations(tmp_path: Path) -> None:
    assert ev.main([str(tmp_path)]) == 1
