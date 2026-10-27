"""Key and chord estimation with Essentia (AGPL-3.0, optional ``essentia`` extra).

* Key: ``KeyExtractor`` with the ``bgate`` profile is the primary estimate. A small panel of other
  profiles and a chord-based tonic hint decide whether the song is ambiguous (typically between
  a major key and its relative minor, or between a key and its dominant); when it is, the second
  candidate is returned as ``KeyInfo.alternative`` instead of pretending to know.
* Chords: HPCP frames, ``ChordsDetectionBeats`` aligned to the detected beats, then smoothed into
  segments.

The functions that do not touch Essentia (segmenting, tonic hint, decision) are pure and take
plain data, so they are tested with synthetic input.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from audio_core.constants import SAMPLE_RATE
from audio_core.models import Chord, KeyAlternative, KeyInfo

CHORDS_VERSION = "1"

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

# Primary profile and the panel used to find a runner-up. ``bgate`` is Essentia's default and was
# built for modern popular music; the others only vote for the runner-up and never for the primary.
PRIMARY_PROFILE = "bgate"
PANEL_PROFILES = ("bgate", "edma", "braw", "temperley", "krumhansl", "noland", "shaath")
# The runner-up panel key counts as "close" when its summed strength is at least this share of the
# primary key's.
CLOSE_VOTE_RATIO = 0.6
# The chord-based key replaces the profile key only when it covers the chords at least this much
# better (score is 0-1.75: diatonic coverage + tonic evidence). Otherwise it is the alternative.
CHORD_OVERRIDE_MARGIN = 0.15

# HPCP settings tuned on a full-mix pop song: a bass-to-vocal band with four harmonics, 8192-sample
# frames and a non-linear magnitude weighting keep drums and sibilance out of the chord templates.
HPCP_SIZE = 36
HPCP_FRAME = 8192
HPCP_HOP = 2048
HPCP_MIN_HZ = 60
HPCP_MAX_HZ = 2000
HPCP_HARMONICS = 4
# Chord runs shorter than this many beats are absorbed by a neighbour: per-beat templates flicker
# on full mixes, and a real chord lasts at least half a bar in anything the studio plays.
MIN_CHORD_BEATS = 2

_MAJOR_DEGREES = {0: "M", 2: "m", 4: "m", 5: "M", 7: "M", 9: "m"}
_MINOR_DEGREES = {0: "m", 3: "M", 5: "m", 7: "m", 8: "M", 10: "M"}
# Weights of the chord-based tonic score: coverage dominates, tonic and cadences break ties
# between relative keys, which share every diatonic chord.
_W_TONIC = 0.5
_W_CADENCE = 0.5
_W_FINAL = 0.25


@dataclass(frozen=True)
class KeyCandidate:
    pitch_class: int
    mode: str  # "major" | "minor"
    strength: float = 0.0


@dataclass(frozen=True)
class ChordHint:
    pitch_class: int
    mode: str
    score: float
    # Score of the chord set against the profile key, to compare with ``score``.
    runner_up_score: float


def sharp_name(name: str) -> str:
    return _FLAT_TO_SHARP.get(name, name)


def parse_chord(label: str) -> tuple[int, str] | None:
    """(pitch class, "M" | "m") of an Essentia label (``A``, ``Bbm``); None for no chord."""
    if not label or label == "N":
        return None
    minor = label.endswith("m")
    root = sharp_name(label[:-1] if minor else label)
    if root not in PITCH_CLASSES:
        return None
    return PITCH_CLASSES.index(root), "m" if minor else "M"


def format_chord(pitch_class: int, quality: str) -> str:
    return PITCH_CLASSES[pitch_class] + ("m" if quality == "m" else "")


# --- Chord segments (pure) -----------------------------------------------------------------


def chord_segments(
    labels: Sequence[str], beats: Sequence[float], *, min_beats: int = MIN_CHORD_BEATS
) -> list[Chord]:
    """Merge per-beat labels into segments; ``labels[i]`` spans ``beats[i]`` to ``beats[i + 1]``.

    Repeats merge, then runs shorter than ``min_beats`` are absorbed by the longer neighbour
    (the earlier one on a tie), shortest first, so one-beat flicker never reaches the studio.
    "No chord" spans stay out of the result.
    """
    n = min(len(labels), len(beats) - 1)
    if n <= 0:
        return []
    names: list[str | None] = []
    for label in labels[:n]:
        parsed = parse_chord(label)
        names.append(None if parsed is None else format_chord(*parsed))
    runs: list[list] = []  # [label, first beat index, beat count]
    for i, name in enumerate(names):
        if runs and runs[-1][0] == name:
            runs[-1][2] += 1
        else:
            runs.append([name, i, 1])
    while len(runs) > 1:
        shortest = min(range(len(runs)), key=lambda k: (runs[k][2], k))
        if runs[shortest][2] >= min_beats:
            break
        left = runs[shortest - 1] if shortest > 0 else None
        right = runs[shortest + 1] if shortest + 1 < len(runs) else None
        target = left if right is None or (left is not None and left[2] >= right[2]) else right
        assert target is not None
        runs[shortest][0] = target[0]
        # Re-merge the equal neighbours this absorption created.
        merged: list[list] = []
        for run in runs:
            if merged and merged[-1][0] == run[0]:
                merged[-1][2] += run[2]
            else:
                merged.append(run)
        runs = merged
    return [
        Chord(
            start=round(float(beats[first]), 3),
            end=round(float(beats[first + count]), 3),
            label=name,
        )
        for name, first, count in runs
        if name is not None
    ]


# --- Tonic hint from chords (pure) ---------------------------------------------------------


def _key_chords(pitch_class: int, mode: str) -> dict[tuple[int, str], float]:
    degrees = _MAJOR_DEGREES if mode == "major" else _MINOR_DEGREES
    chords = {((pitch_class + d) % 12, q): 1.0 for d, q in degrees.items()}
    if mode == "minor":  # the dominant of a minor key is usually played major
        chords[((pitch_class + 7) % 12, "M")] = 1.0
    return chords


def _score_key(
    durations: dict[tuple[int, str], float],
    total: float,
    last: tuple[int, str] | None,
    cadences: dict[tuple[int, str], float],
    pitch_class: int,
    mode: str,
) -> float:
    diatonic = _key_chords(pitch_class, mode)
    coverage = sum(d for chord, d in durations.items() if chord in diatonic) / total
    tonic = (pitch_class, "M" if mode == "major" else "m")
    tonic_share = durations.get(tonic, 0.0) / total
    cadence_total = sum(cadences.values())
    cadence_share = cadences.get(tonic, 0.0) / cadence_total if cadence_total else 0.0
    final = 1.0 if last == tonic else 0.0
    return (
        coverage + _W_TONIC * tonic_share + _W_CADENCE * cadence_share * coverage + _W_FINAL * final
    )


def chord_key_hint(
    chords: Sequence[Chord], reference: KeyCandidate | None = None
) -> ChordHint | None:
    """Best key for a chord sequence: diatonic coverage, tonic time, V-I cadences, final chord.

    ``reference`` is the profile key; the hint carries its score as ``runner_up_score`` so the
    caller can tell a real disagreement from a tie between relative keys.
    """
    durations: Counter = Counter()
    parsed: list[tuple[int, str]] = []
    for chord in chords:
        key = parse_chord(chord.label)
        if key is None or chord.end <= chord.start:
            continue
        durations[key] += chord.end - chord.start
        parsed.append(key)
    total = float(sum(durations.values()))
    if total <= 0:
        return None
    # Cadence evidence: the chord arrived at from the chord a fifth above it (V-I, v-i).
    cadences: Counter = Counter()
    for (root_a, _), (root_b, quality_b) in zip(parsed, parsed[1:], strict=False):
        if (root_a - root_b) % 12 == 7:
            cadences[(root_b, quality_b)] += 1.0
    last = parsed[-1] if parsed else None
    scores = {
        (pc, mode): _score_key(durations, total, last, cadences, pc, mode)
        for pc in range(12)
        for mode in ("major", "minor")
    }
    (pc, mode), best = max(scores.items(), key=lambda item: item[1])
    ref_score = scores[(reference.pitch_class, reference.mode)] if reference else 0.0
    return ChordHint(pc, mode, round(best, 4), round(ref_score, 4))


# --- Key decision (pure) -------------------------------------------------------------------


def _camelot(pitch_class: int, mode: str) -> str:
    major_pc = pitch_class if mode == "major" else (pitch_class + 3) % 12
    return f"{(8 + 7 * major_pc - 1) % 12 + 1}{'B' if mode == 'major' else 'A'}"


def _alternative(pitch_class: int, mode: str) -> KeyAlternative:
    return KeyAlternative(
        key=PITCH_CLASSES[pitch_class], mode=mode, camelot=_camelot(pitch_class, mode)
    )


def decide_key(
    primary: KeyCandidate,
    panel: Sequence[KeyCandidate],
    hint: ChordHint | None,
) -> tuple[KeyCandidate, KeyAlternative | None, str]:
    """Pick the primary key and, when doubtful, the alternative; the third item says why.

    1. The chord hint disagrees with the profile key: it becomes the primary only if it covers
       the chords clearly better (``CHORD_OVERRIDE_MARGIN``); otherwise it is the alternative.
    2. No chord disagreement, but the panel's runner-up has at least ``CLOSE_VOTE_RATIO`` of the
       primary's votes: the runner-up is the alternative.
    """
    if hint is not None and (hint.pitch_class, hint.mode) != (primary.pitch_class, primary.mode):
        chord_key = KeyCandidate(hint.pitch_class, hint.mode, primary.strength)
        if hint.score - hint.runner_up_score >= CHORD_OVERRIDE_MARGIN:
            return (
                chord_key,
                _alternative(primary.pitch_class, primary.mode),
                "chords fit the other key clearly better",
            )
        return (
            primary,
            _alternative(hint.pitch_class, hint.mode),
            "chords point to a different key",
        )
    votes: Counter = Counter()
    for candidate in panel:
        votes[(candidate.pitch_class, candidate.mode)] += candidate.strength
    own = votes.get((primary.pitch_class, primary.mode), 0.0)
    rivals = [(v, k) for k, v in votes.items() if k != (primary.pitch_class, primary.mode)]
    if own > 0 and rivals:
        best_votes, (pc, mode) = max(rivals)
        if best_votes >= CLOSE_VOTE_RATIO * own:
            return primary, _alternative(pc, mode), "key profiles are split"
    return primary, None, ""


# --- Essentia ------------------------------------------------------------------------------


def _essentia():
    import essentia.standard as es

    return es


def essentia_version() -> str:
    from importlib import metadata

    try:
        return metadata.version("essentia")
    except metadata.PackageNotFoundError:
        return "unknown"


def _key_candidate(mono: np.ndarray, profile: str) -> KeyCandidate | None:
    es = _essentia()
    key, scale, strength = es.KeyExtractor(sampleRate=SAMPLE_RATE, profileType=profile)(mono)
    name = sharp_name(key)
    if name not in PITCH_CLASSES or scale not in ("major", "minor"):
        return None
    return KeyCandidate(PITCH_CLASSES.index(name), scale, max(0.0, min(1.0, float(strength))))


def estimate_key_with_chords(
    mono: np.ndarray, chords: Sequence[Chord] | None
) -> tuple[KeyCandidate | None, KeyInfo | None, str]:
    """Primary key from Essentia plus the doubt around it. Returns (candidate, info, reason)."""
    from audio_core.analysis import compatible_codes

    primary = _key_candidate(mono, PRIMARY_PROFILE)
    if primary is None:
        return None, None, ""
    panel = [c for p in PANEL_PROFILES if (c := _key_candidate(mono, p)) is not None]
    hint = chord_key_hint(chords, primary) if chords else None
    chosen, alternative, reason = decide_key(primary, panel, hint)
    code = _camelot(chosen.pitch_class, chosen.mode)
    # Confidence is the strongest profile that actually voted for the chosen key; a key chosen from
    # the chords alone, with no profile behind it, carries none.
    behind = [
        c.strength
        for c in (primary, *panel)
        if (c.pitch_class, c.mode) == (chosen.pitch_class, chosen.mode)
    ]
    info = KeyInfo(
        key=PITCH_CLASSES[chosen.pitch_class],
        mode=chosen.mode,
        camelot=code,
        compatible=compatible_codes(code),
        confidence=round(max(behind), 3) if behind else None,
        alternative=alternative,
    )
    return chosen, info, reason


def compute_hpcp(mono: np.ndarray) -> np.ndarray:
    """HPCP frames (``HPCP_SIZE`` bins) of a mono signal at ``SAMPLE_RATE``."""
    es = _essentia()
    window = es.Windowing(type="blackmanharris62")
    spectrum = es.Spectrum()
    peaks = es.SpectralPeaks(
        orderBy="magnitude",
        magnitudeThreshold=1e-5,
        minFrequency=HPCP_MIN_HZ,
        maxFrequency=HPCP_MAX_HZ,
        maxPeaks=100,
        sampleRate=SAMPLE_RATE,
    )
    hpcp = es.HPCP(
        size=HPCP_SIZE,
        referenceFrequency=440,
        bandPreset=False,
        minFrequency=HPCP_MIN_HZ,
        maxFrequency=HPCP_MAX_HZ,
        weightType="squaredCosine",
        nonLinear=True,
        harmonics=HPCP_HARMONICS,
        windowSize=1.0,
        sampleRate=SAMPLE_RATE,
    )
    frames = []
    for frame in es.FrameGenerator(
        mono, frameSize=HPCP_FRAME, hopSize=HPCP_HOP, startFromZero=True
    ):
        freqs, mags = peaks(spectrum(window(frame)))
        frames.append(hpcp(freqs, mags))
    return np.array(frames, dtype=np.float32)


def detect_chords(
    mono: np.ndarray, beats: Sequence[float], *, start_at: float | None = None
) -> list[Chord]:
    """Beat-aligned chord segments of a mono signal; empty when there are fewer than 3 beats.

    ``start_at`` skips beats before it: the grid extrapolated over a beatless intro has no real
    beats there, and a chord label per invented beat would be noise.
    """
    if start_at is not None:
        beats = [b for b in beats if b >= start_at - 1e-3]
    if len(beats) < 3:
        return []
    es = _essentia()
    pcp = compute_hpcp(mono)
    if pcp.shape[0] == 0:
        return []
    ticks = np.asarray(beats, dtype=np.float32)
    labels, _strength = es.ChordsDetectionBeats(
        hopSize=HPCP_HOP, sampleRate=SAMPLE_RATE, chromaPick="interbeat_median"
    )(pcp, ticks)
    return chord_segments(list(labels), list(beats))
