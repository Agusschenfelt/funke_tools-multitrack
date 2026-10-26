"""Song section detection: bar-level Laplacian segmentation.

The pipeline works on the bar grid produced by ``analysis`` (consecutive downbeats), so every
boundary is a bar start by construction.

1. Features per bar: CQT chroma and MFCCs are computed on 11.025 kHz mono audio, aggregated per
   beat with a median and then per bar with a median (beat-synchronous). RMS is averaged per bar.
   Each feature is standardized across bars and the chroma and timbre (MFCC + log RMS) blocks are
   weighted so both contribute equally.
2. Recurrence: a k-nearest-neighbor affinity matrix over bars (``librosa.segment.recurrence_matrix``
   in ``affinity`` mode), smoothed along diagonals so that repeated passages light up as paths,
   plus a local path term linking consecutive bars. The two are mixed per bar by their degrees, as
   in McFee and Ellis, "Analyzing song structure with spectral clustering" (ISMIR 2014) and the
   librosa "Laplacian segmentation" example.
3. Spectral clustering: eigenvectors of the normalized graph Laplacian; ``k`` in
   ``MIN_CLUSTERS..MAX_CLUSTERS`` is the one with the largest eigengap; a small deterministic
   k-means (farthest-point initialization, no randomness) assigns a cluster to every bar.
4. Segments are runs of one cluster. Clustering uses features averaged over a window of
   ``CONTEXT_BARS`` bars, which blurs boundaries, so each boundary is afterwards moved by at most
   ``REFINE_BARS`` bars to the largest change of the unsmoothed features.
   Segments are runs of one cluster. Segments shorter than ``MIN_SEGMENT_BARS`` are merged into
   the more similar neighbor (cosine similarity of mean bar features) until none remain.

Functional labels (``label_segments``) are heuristic, versioned by ``HEURISTICS_VERSION`` and only
suggestions; each carries a confidence in 0..1. ``e`` below is ``Segment.energy`` (1.0 = song
mean), ``vocal`` the fraction of vocal bars (None when no vocal stem was given). Rules apply in
this order, and a segment keeps the first label that matches:

1. intro: first segment, ``e < LOW_ENERGY`` and (vocals unknown or ``vocal < NO_VOCALS``).
2. outro: last segment, ``e < LOW_ENERGY``.
3. chorus: among the remaining clusters that occur at least twice, the one with the highest
   ``occurrences * mean energy * (1 + mean vocal)`` (the vocal factor is 1 when unknown).
4. pre_chorus: at most ``PRE_CHORUS_MAX_BARS`` bars, shorter than the chorus right after it, and
   energy between the previous segment's and that chorus's (rising into the chorus).
5. bridge: a cluster that occurs once with a chorus somewhere before and after it.
6. break: a cluster that occurs once, at most ``BREAK_MAX_BARS`` bars and ``e < BREAK_ENERGY``.
7. Vocals known and absent (``vocal < NO_VOCALS``): solo when ``e >= SOLO_ENERGY``, else
   instrumental.
8. Everything else is verse: the first one in the song is ``verse``, every later one
   ``verse_2`` (the vocabulary has no third verse).
A song with a single segment is one low-confidence verse.

Degenerate audio (digital silence, or a constant tone whose features do not vary from bar to bar)
has no estimable structure: it is reported as a single segment, hence one low-confidence verse,
instead of clustering numerical noise. Non-finite features raise ``SectionsError``.

Confidence is ``base + spread * margin`` with the margin clipped to 0..1 (see ``_confidence``).
The margin is how far the deciding feature is from its threshold (energy for intro and outro, the
cluster's share of the chorus score, how much energy rises into the chorus, how absent the vocals
are). Labels whose rule used vocals, or that assume them, are multiplied by ``UNKNOWN_VOCALS``
when no vocal stem was given.

Heavy imports (librosa) stay inside the functions that need them, as in ``analysis``.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from audio_core.analysis import _package_version, to_mono
from audio_core.constants import SAMPLE_RATE
from audio_core.extras import require
from audio_core.models import Grid, ModelVersion, Section, SectionName, Sections, StemSet

HEURISTICS_VERSION = "1"

FEATURE_RATE = 11025
FEATURE_HOP = 512
N_MFCC = 13
MIN_CLUSTERS = 3
MAX_CLUSTERS = 8
MIN_SEGMENT_BARS = 4
# Below this many bars the structure is not estimable: the song is one segment.
MIN_BARS_FOR_SEGMENTATION = 8
# A trailing partial bar shorter than this fraction of the median bar is folded into the last bar.
MIN_LAST_BAR_FRACTION = 0.5
# A bar counts as vocal when its vocal RMS exceeds this fraction of the loudest vocal bar.
VOCAL_BAR_RELATIVE_RMS = 0.1
VOCAL_BAR_ABSOLUTE_RMS = 1e-4
# Clustering sees each bar through a window of this many bars (one before, the rest after), so a
# chord progression that changes every bar is one texture instead of one cluster per chord.
CONTEXT_BARS = 4
CONTEXT_BEFORE = 1
# Boundaries are moved up to this many bars to the strongest change in the unsmoothed features.
REFINE_BARS = 2
KMEANS_ITERATIONS = 100
# Label thresholds (see the module docstring).
LOW_ENERGY = 0.8
SOLO_ENERGY = 1.3
BREAK_ENERGY = 0.5
NO_VOCALS = 0.25
PRE_CHORUS_MAX_BARS = 8
BREAK_MAX_BARS = 8
UNKNOWN_VOCALS = 0.85
FEATURE_EPSILON = 1e-8
# A vocal stem may differ from the mix by up to this many seconds (decoder padding, separation
# rounding); it is padded with silence or trimmed to the mix length. More is a real mismatch.
VOCAL_LENGTH_TOLERANCE = 0.5
# Silent or constant audio: no bar-to-bar variation in the features (chroma is in 0..1, MFCCs are
# in dB-like units), so any clustering would only amplify numerical noise.
FLAT_CHROMA_STD = 1e-3
FLAT_TIMBRE_STD = 1e-2


class SectionsError(ValueError):
    """Raised when sections cannot be detected from the given audio and grid."""


@dataclass(frozen=True)
class Segment:
    """A run of bars sharing one structural cluster.

    ``start_bar`` and ``end_bar`` index bars (``end_bar`` is exclusive); seconds are original-song
    time. ``energy`` is the mean bar RMS relative to the song mean (1.0 = average loudness).
    ``vocal`` is the fraction of bars with vocals, or None when no vocal stem was given.
    """

    start_bar: int
    end_bar: int
    start: float
    end: float
    cluster: int
    energy: float
    vocal: float | None

    @property
    def n_bars(self) -> int:
        return self.end_bar - self.start_bar


@dataclass(frozen=True)
class BarFeatures:
    chroma: np.ndarray  # (12, bars)
    timbre: np.ndarray  # (N_MFCC - 1 + 1, bars): MFCC 1.. plus log RMS
    rms: np.ndarray  # (bars,), linear
    vocal_rms: np.ndarray | None  # (bars,), linear
    edges: np.ndarray  # (bars + 1,) bar boundaries in seconds


# --- Bars and features ---------------------------------------------------------------------


def bar_edges(grid: Grid, duration: float) -> np.ndarray:
    """Bar boundaries in seconds: each downbeat starts a bar, the last one runs to ``duration``.

    A trailing partial bar shorter than half the median bar is folded into the previous bar.
    """
    downbeats = np.asarray(grid.downbeats, dtype=np.float64)
    if downbeats.size == 0:
        raise SectionsError("grid has no downbeats; section detection needs a bar grid")
    downbeats = downbeats[downbeats < duration]
    if downbeats.size == 0:
        raise SectionsError("all downbeats fall after the end of the audio")
    edges = np.append(downbeats, duration)
    if edges.size > 2:
        median_bar = float(np.median(np.diff(edges[:-1])))
        if edges[-1] - edges[-2] < MIN_LAST_BAR_FRACTION * median_bar:
            edges = np.delete(edges, -2)
    return edges


def _standardize(block: np.ndarray) -> np.ndarray:
    """Z-score each row across bars and scale so the block has unit total variance per bar."""
    centered = block - block.mean(axis=1, keepdims=True)
    scaled = centered / np.maximum(block.std(axis=1, keepdims=True), FEATURE_EPSILON)
    return scaled / np.sqrt(block.shape[0])


def _per_bar_median(feature: np.ndarray, frame_times: np.ndarray, grid: Grid, edges: np.ndarray):
    """Beat-synchronous aggregation: median per beat, then median over the beats of each bar."""
    beats = np.asarray(grid.beats, dtype=np.float64)
    out = np.zeros((feature.shape[0], edges.size - 1))
    for bar in range(edges.size - 1):
        lo, hi = edges[bar], edges[bar + 1]
        cuts = np.concatenate(([lo], beats[(beats > lo) & (beats < hi)], [hi]))
        columns = []
        for a, b in zip(cuts[:-1], cuts[1:], strict=True):
            mask = (frame_times >= a) & (frame_times < b)
            if mask.any():
                columns.append(np.median(feature[:, mask], axis=1))
        if columns:
            out[:, bar] = np.median(np.stack(columns, axis=1), axis=1)
    return out


def _fit_vocals(vocals: np.ndarray, samples: int) -> np.ndarray:
    """Pad with silence or trim the vocal stem to ``samples``; a large mismatch is an error."""
    difference = vocals.shape[-1] - samples
    if abs(difference) > VOCAL_LENGTH_TOLERANCE * SAMPLE_RATE:
        raise SectionsError(
            f"vocal stem is {vocals.shape[-1] / SAMPLE_RATE:.2f} s but the audio is "
            f"{samples / SAMPLE_RATE:.2f} s; they must match within {VOCAL_LENGTH_TOLERANCE} s"
        )
    if difference > 0:
        return vocals[..., :samples]
    pad = [(0, 0)] * (vocals.ndim - 1) + [(0, -difference)]
    return np.pad(vocals, pad)


def _vocal_rms(vocals: np.ndarray, edges: np.ndarray) -> np.ndarray:
    mono = to_mono(vocals) if vocals.ndim == 2 else vocals.astype(np.float32, copy=False)
    out = np.zeros(edges.size - 1)
    for bar in range(edges.size - 1):
        lo = int(round(edges[bar] * SAMPLE_RATE))
        hi = int(round(edges[bar + 1] * SAMPLE_RATE))
        chunk = mono[lo:hi]
        if chunk.size:
            out[bar] = float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))
    return out


def extract_bar_features(
    audio: np.ndarray, grid: Grid, *, vocals: np.ndarray | None = None
) -> BarFeatures:
    """Chroma, timbre and loudness per bar, plus vocal loudness per bar when a stem is given."""
    librosa = require("librosa")

    mono = to_mono(audio) if audio.ndim == 2 else audio.astype(np.float32, copy=False)
    duration = mono.size / SAMPLE_RATE
    edges = bar_edges(grid, duration)
    if vocals is not None:
        vocals = _fit_vocals(vocals, mono.size)
    y = librosa.resample(mono, orig_sr=SAMPLE_RATE, target_sr=FEATURE_RATE)
    chroma = librosa.feature.chroma_cqt(y=y, sr=FEATURE_RATE, hop_length=FEATURE_HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=FEATURE_RATE, hop_length=FEATURE_HOP, n_mfcc=N_MFCC)
    rms = librosa.feature.rms(y=y, hop_length=FEATURE_HOP)
    frame_times = librosa.frames_to_time(
        np.arange(chroma.shape[1]), sr=FEATURE_RATE, hop_length=FEATURE_HOP
    )
    bar_chroma = _per_bar_median(chroma, frame_times, grid, edges)
    bar_mfcc = _per_bar_median(mfcc[1:], frame_times, grid, edges)
    bar_rms = _per_bar_median(rms, frame_times, grid, edges)[0]
    timbre = np.vstack([bar_mfcc, np.log(bar_rms + FEATURE_EPSILON)[None, :]])
    return BarFeatures(
        chroma=bar_chroma,
        timbre=timbre,
        rms=bar_rms,
        vocal_rms=None if vocals is None else _vocal_rms(vocals, edges),
        edges=edges,
    )


def is_flat(features: BarFeatures) -> bool:
    """True when the features barely vary across bars (silence or a constant tone)."""
    return (
        float(features.chroma.std(axis=1).max()) < FLAT_CHROMA_STD
        and float(features.timbre.std(axis=1).max()) < FLAT_TIMBRE_STD
    )


def feature_matrix(features: BarFeatures) -> np.ndarray:
    """Standardized (dims, bars) matrix with the chroma and timbre blocks equally weighted."""
    return np.vstack([_standardize(features.chroma), _standardize(features.timbre)])


# --- Laplacian segmentation -----------------------------------------------------------------


def bar_affinity(x: np.ndarray) -> np.ndarray:
    """Mix of the path-enhanced recurrence affinity and a sequential path term, (bars, bars)."""
    librosa = require("librosa")
    from scipy.signal import convolve2d

    n = x.shape[1]
    recurrence = librosa.segment.recurrence_matrix(
        x, mode="affinity", metric="euclidean", sym=True, width=3 if n > 8 else 1
    )
    recurrence = np.asarray(recurrence, dtype=np.float64)
    # Repeats of a passage appear as diagonal stripes; averaging along the diagonal keeps them
    # and suppresses isolated coincidences.
    recurrence = convolve2d(recurrence, np.eye(3) / 3.0, mode="same")
    recurrence = (recurrence + recurrence.T) / 2.0

    step = np.sum(np.square(x[:, :-1] - x[:, 1:]), axis=0)
    sigma = float(np.median(step))
    path_similarity = np.exp(-step / sigma) if sigma > FEATURE_EPSILON else np.ones(n - 1)
    path = np.diag(path_similarity, k=1) + np.diag(path_similarity, k=-1)

    path_degree = path.sum(axis=1)
    recurrence_degree = recurrence.sum(axis=1)
    mu = (path_degree / (path_degree + recurrence_degree + FEATURE_EPSILON))[:, None]
    mixed = mu * path + (1.0 - mu) * recurrence
    return (mixed + mixed.T) / 2.0


def spectral_embedding(affinity: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Eigenvalues (ascending) and eigenvectors of the normalized Laplacian of ``affinity``."""
    from scipy.sparse import csgraph

    laplacian = csgraph.laplacian(affinity, normed=True)
    values, vectors = np.linalg.eigh(laplacian)
    return values, vectors


def choose_k(eigenvalues: np.ndarray, n_bars: int) -> int:
    """Number of clusters: the largest eigengap among ``MIN_CLUSTERS..MAX_CLUSTERS``.

    ``k`` bars-bounded: at most one cluster per two bars so every cluster can span a segment.
    """
    k_max = max(1, min(MAX_CLUSTERS, n_bars // 2, eigenvalues.size - 1))
    k_min = min(MIN_CLUSTERS, k_max)
    candidates = np.arange(k_min, k_max + 1)
    gaps = eigenvalues[candidates] - eigenvalues[candidates - 1]
    return int(candidates[int(np.argmax(gaps))])


def kmeans(points: np.ndarray, k: int) -> np.ndarray:
    """Deterministic k-means: farthest-point initialization from the first point, Lloyd steps."""
    centers = [points[0]]
    for _ in range(1, k):
        distance = np.min([np.sum((points - c) ** 2, axis=1) for c in centers], axis=0)
        centers.append(points[int(np.argmax(distance))])
    centers_array = np.stack(centers)
    labels = np.zeros(points.shape[0], dtype=int)
    for _ in range(KMEANS_ITERATIONS):
        distances = np.sum((points[:, None, :] - centers_array[None, :, :]) ** 2, axis=2)
        new_labels = np.argmin(distances, axis=1)
        for cluster in range(k):
            members = points[new_labels == cluster]
            if members.size:
                centers_array[cluster] = members.mean(axis=0)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
    return labels


def context_window(x: np.ndarray) -> np.ndarray:
    """Mean of each bar's features over ``CONTEXT_BARS`` bars (clipped at the song edges)."""
    n = x.shape[1]
    out = np.zeros_like(x)
    for i in range(n):
        lo = max(0, i - CONTEXT_BEFORE)
        hi = min(n, i - CONTEXT_BEFORE + CONTEXT_BARS)
        out[:, i] = x[:, lo:hi].mean(axis=1)
    return out


def cluster_bars(x: np.ndarray) -> np.ndarray:
    """Cluster id per bar, numbered by order of first appearance."""
    affinity = bar_affinity(context_window(x))
    values, vectors = spectral_embedding(affinity)
    k = choose_k(values, x.shape[1])
    embedding = vectors[:, :k]
    norms = np.maximum(np.linalg.norm(embedding, axis=1, keepdims=True), FEATURE_EPSILON)
    labels = kmeans(embedding / norms, k)
    order = {label: i for i, label in enumerate(dict.fromkeys(labels.tolist()))}
    return np.array([order[label] for label in labels.tolist()], dtype=int)


# --- Segments -------------------------------------------------------------------------------


def _runs(labels: np.ndarray) -> list[list[int]]:
    """[start, end, cluster] runs of identical consecutive labels."""
    runs: list[list[int]] = []
    for i, label in enumerate(labels.tolist()):
        if runs and runs[-1][2] == label:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1, label])
    return runs


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b) / denominator if denominator > FEATURE_EPSILON else 0.0


def merge_short_runs(runs: list[list[int]], x: np.ndarray) -> list[list[int]]:
    """Merge runs shorter than ``MIN_SEGMENT_BARS`` into the more similar neighbor.

    The shortest offending run goes first (earliest on ties). A run at either end has only one
    neighbor. Runs that end up adjacent with the same cluster are coalesced.
    """
    runs = [run[:] for run in runs]
    while len(runs) > 1:
        short = [i for i, (a, b, _) in enumerate(runs) if b - a < MIN_SEGMENT_BARS]
        if not short:
            break
        i = min(short, key=lambda j: (runs[j][1] - runs[j][0], j))
        mean = x[:, runs[i][0] : runs[i][1]].mean(axis=1)
        neighbors = [j for j in (i - 1, i + 1) if 0 <= j < len(runs)]
        best = max(
            neighbors,
            key=lambda j: (_cosine(mean, x[:, runs[j][0] : runs[j][1]].mean(axis=1)), -j),
        )
        runs[best][0] = min(runs[best][0], runs[i][0])
        runs[best][1] = max(runs[best][1], runs[i][1])
        del runs[i]
        merged: list[list[int]] = []
        for run in runs:
            if merged and merged[-1][2] == run[2]:
                merged[-1][1] = run[1]
            else:
                merged.append(run)
        runs = merged
    return runs


def refine_boundaries(runs: list[list[int]], x: np.ndarray) -> list[list[int]]:
    """Move each boundary up to ``REFINE_BARS`` bars to where the features change the most.

    The change at a candidate boundary is the distance between the mean features of up to
    ``CONTEXT_BARS`` bars on each side, never reaching into the neighboring segments. Moves that
    would empty a segment are not considered; ties keep the smallest move. This runs before short
    segments are merged, so a section the blurred clustering cut short can regain its length.
    """
    runs = [run[:] for run in runs]
    for i in range(len(runs) - 1):
        boundary = runs[i][1]
        lo_limit, hi_limit = runs[i][0], runs[i + 1][1]
        best, best_key = boundary, None
        for candidate in range(boundary - REFINE_BARS, boundary + REFINE_BARS + 1):
            if candidate <= lo_limit or candidate >= hi_limit:
                continue
            left = x[:, max(lo_limit, candidate - CONTEXT_BARS) : candidate].mean(axis=1)
            right = x[:, candidate : min(hi_limit, candidate + CONTEXT_BARS)].mean(axis=1)
            key = (float(np.linalg.norm(left - right)), -abs(candidate - boundary))
            if best_key is None or key > best_key:
                best, best_key = candidate, key
        runs[i][1] = runs[i + 1][0] = best
    return runs


def segment_song(
    audio: np.ndarray, grid: Grid, *, vocals: np.ndarray | None = None
) -> list[Segment]:
    """Split a song into segments on bar starts.

    ``audio`` and ``vocals`` are float32 at ``SAMPLE_RATE``, mono or (channels, samples).
    Raises ``SectionsError`` when the grid has no usable downbeats.
    """
    features = extract_bar_features(audio, grid, vocals=vocals)
    n_bars = features.rms.size
    x = feature_matrix(features)
    if not np.isfinite(x).all():
        raise SectionsError("audio produced non-finite features; cannot detect sections")
    if n_bars < MIN_BARS_FOR_SEGMENTATION or is_flat(features):
        runs = [[0, n_bars, 0]]
    else:
        runs = merge_short_runs(refine_boundaries(_runs(cluster_bars(x)), x), x)
        # Cluster ids are renumbered after merging so they stay dense and ordered.
        order = {c: i for i, c in enumerate(dict.fromkeys(run[2] for run in runs))}
        runs = [[a, b, order[c]] for a, b, c in runs]

    mean_rms = float(features.rms.mean()) or 1.0
    vocal_active = None
    if features.vocal_rms is not None:
        peak = float(features.vocal_rms.max())
        vocal_active = (features.vocal_rms > VOCAL_BAR_RELATIVE_RMS * peak) & (
            features.vocal_rms > VOCAL_BAR_ABSOLUTE_RMS
        )
    return [
        Segment(
            start_bar=a,
            end_bar=b,
            start=float(features.edges[a]),
            end=float(features.edges[b]),
            cluster=cluster,
            energy=float(features.rms[a:b].mean() / mean_rms),
            vocal=None if vocal_active is None else float(vocal_active[a:b].mean()),
        )
        for a, b, cluster in runs
    ]


# --- Labels ---------------------------------------------------------------------------------


def _confidence(base: float, spread: float, margin: float, *, vocals_known: bool, uses_vocals=True):
    """``base + spread * clip(margin, 0, 1)``, discounted when the rule relied on missing vocals."""
    value = base + spread * min(max(margin, 0.0), 1.0)
    return round(value if vocals_known or not uses_vocals else value * UNKNOWN_VOCALS, 2)


def _is_silent(segment: Segment) -> bool:
    return segment.vocal is not None and segment.vocal < NO_VOCALS


def label_segments(segments: list[Segment]) -> list[tuple[SectionName, float]]:
    """Heuristic (name, confidence) per segment; see the module docstring for the rules."""
    n = len(segments)
    known = segments[0].vocal is not None if segments else False
    labels: list[tuple[SectionName, float] | None] = [None] * n
    if n == 1:
        return [(SectionName.VERSE, 0.2)]

    first, last = segments[0], segments[-1]
    if first.energy < LOW_ENERGY and (first.vocal is None or first.vocal < NO_VOCALS):
        margin = (LOW_ENERGY - first.energy) / LOW_ENERGY
        labels[0] = (SectionName.INTRO, _confidence(0.5, 0.5, margin, vocals_known=known))
    if last.energy < LOW_ENERGY:
        margin = (LOW_ENERGY - last.energy) / LOW_ENERGY
        labels[-1] = (
            SectionName.OUTRO,
            _confidence(0.5, 0.5, margin, vocals_known=known, uses_vocals=False),
        )

    free = [i for i in range(n) if labels[i] is None]
    members: dict[int, list[int]] = {}
    for i in free:
        members.setdefault(segments[i].cluster, []).append(i)
    occurrences = {c: [segments[i] for i in idx] for c, idx in members.items()}

    scores: dict[int, float] = {}
    for cluster, segs in occurrences.items():
        if len(segs) < 2:
            continue
        bars = sum(s.n_bars for s in segs)
        energy = sum(s.energy * s.n_bars for s in segs) / bars
        vocal = sum((s.vocal or 0.0) * s.n_bars for s in segs) / bars
        scores[cluster] = len(segs) * energy * (1.0 + vocal)
    chorus_cluster = max(scores, key=lambda c: (scores[c], -c)) if scores else None
    if chorus_cluster is not None:
        share = scores[chorus_cluster] / sum(scores.values())
        confidence = _confidence(0.4, 0.5, share, vocals_known=known)
        for i in members[chorus_cluster]:
            labels[i] = (SectionName.CHORUS, confidence)

    is_chorus = [label is not None and label[0] is SectionName.CHORUS for label in labels]
    for i in range(1, n - 1):
        seg, following = segments[i], segments[i + 1]
        if labels[i] is not None or not is_chorus[i + 1]:
            continue
        rising = segments[i - 1].energy <= seg.energy < following.energy
        if seg.n_bars <= PRE_CHORUS_MAX_BARS and seg.n_bars < following.n_bars and rising:
            margin = 2.0 * (following.energy - seg.energy) / following.energy
            labels[i] = (
                SectionName.PRE_CHORUS,
                _confidence(0.45, 0.4, margin, vocals_known=known, uses_vocals=False),
            )

    for i in range(n):
        seg = segments[i]
        if labels[i] is not None or len(members.get(seg.cluster, [])) != 1:
            continue
        if any(is_chorus[:i]) and any(is_chorus[i + 1 :]):
            labels[i] = (SectionName.BRIDGE, 0.6)
        elif seg.n_bars <= BREAK_MAX_BARS and seg.energy < BREAK_ENERGY:
            labels[i] = (SectionName.BREAK, 0.4)

    for i in range(n):
        seg = segments[i]
        if labels[i] is None and _is_silent(seg):
            name = SectionName.SOLO if seg.energy >= SOLO_ENERGY else SectionName.INSTRUMENTAL
            labels[i] = (
                name,
                _confidence(0.5, 0.4, 1.0 - (seg.vocal or 0.0) / NO_VOCALS, vocals_known=known),
            )

    seen_verse = False
    for i in range(n):
        if labels[i] is not None:
            continue
        seg = segments[i]
        repeated = len(members.get(seg.cluster, [])) > 1
        if repeated:
            confidence = _confidence(0.45, 0.35, seg.vocal or 0.0, vocals_known=known)
        else:
            confidence = 0.3
        labels[i] = (SectionName.VERSE_2 if seen_verse else SectionName.VERSE, confidence)
        seen_verse = True
    return [label for label in labels if label is not None]


def load_vocal_stem(stemset: StemSet, directory: Path) -> np.ndarray:
    """Read the ``vocals`` stem of a StemSet as float32 (channels, samples) at the internal rate."""
    stem = next((stem for stem in stemset.stems if stem.name == "vocals"), None)
    if stem is None:
        raise SectionsError("the stem set has no 'vocals' stem; omit --stems or separate again")
    path = Path(directory) / stem.path
    try:
        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    except (OSError, RuntimeError) as exc:
        raise SectionsError(f"cannot read vocal stem {path}: {exc}") from exc
    if rate != SAMPLE_RATE:
        raise SectionsError(f"vocal stem {path} is {rate} Hz, expected {SAMPLE_RATE}")
    return np.ascontiguousarray(data.T)


def sections_model_version() -> ModelVersion:
    """The ``models`` record for this method: librosa version plus the heuristics version."""
    return ModelVersion(
        name="librosa-laplacian+heuristics",
        version=f"librosa-{_package_version('librosa')}+heuristics-{HEURISTICS_VERSION}",
        source="bar-level chroma/MFCC recurrence, McFee-Ellis Laplacian segmentation",
    )


def detect_sections(
    audio: np.ndarray,
    grid: Grid,
    *,
    vocals: np.ndarray | None = None,
    source: str | None = None,
) -> Sections:
    """Detect and label the sections of a song; every start is a downbeat time.

    ``vocals`` is an optional vocal stem (same rate as ``audio``, length within
    ``VOCAL_LENGTH_TOLERANCE`` seconds) that sharpens the labels. Raises ``SectionsError`` when the
    grid has no downbeats or the vocal stem length does not match.
    """
    segments = segment_song(audio, grid, vocals=vocals)
    labels = label_segments(segments)
    return Sections(
        source=source,
        sections=[
            Section(
                name=name, start=round(seg.start, 4), confidence=confidence, cluster=seg.cluster
            )
            for seg, (name, confidence) in zip(segments, labels, strict=True)
        ],
    )
